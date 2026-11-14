"""Phase 8B2 subscription tests with explicitly mocked finalized receipts."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.creator_notes.identity import CreatorIdentityService
from services.creator_notes.service import CreatorNotesError, CreatorNotesService
from services.creator_notes.store import CreatorNotesStore
from services.creator_notes.tests.test_paid_research import FakeChain, FakeReader, NOW


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [NOW]
        self.reader = FakeReader()
        self.chain = FakeChain()
        self.store = CreatorNotesStore(f"{self.tmp.name}/creator.sqlite3")
        self.identity = CreatorIdentityService(store=self.store, reader=self.reader, clock=lambda: self.now[0])
        self.auth_tokens = {}
        self.service = CreatorNotesService(
            store=self.store,
            reader=self.reader,
            chain=self.chain,
            radar=self.chain,
            identity=self.identity,
            payment_token="usdc.tidepool-sandbox.testnet",
            clock=lambda: self.now[0],
        )

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def auth_token(self, account: str) -> str:
        challenge = self.service.challenge(account)
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            token = self.service.verify_identity({
                "challenge_id": challenge["challenge_id"],
                "account_id": account,
                "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                "signature": "fixture",
            })["session_token"]
        self.auth_tokens[account] = token
        return token

    def payload(self, label: str) -> dict:
        return {
            "title": f"{label} premium note",
            "thesis": "The stored observation supports a bounded research case.",
            "reference": {"kind": "topic", "id": "cand_1", "label": label},
            "position": "UP",
            "observation_cutoff": "2026-11-13T12:00:00Z",
            "supporting_evidence": [{
                "source_id": "wikimedia:en.wikipedia.org:Bitcoin:2026-11-13",
                "url": "https://pageviews.wmcloud.org/",
                "observed_at": "2026-11-13T00:00:00Z",
                "claim": "The stored Wikimedia window contains the observation.",
            }],
            "contradictory_evidence": [],
            "premium": {
                "enabled": True,
                "body": f"Private subscriber body for {label}.",
                "price": "1.250000",
            },
        }

    def publish_note(self, label: str = "Bitcoin"):
        creator = self.auth_token("creator.testnet")
        self.service.configure_payout(creator)
        draft = self.service.create_draft(creator, self.payload(label))
        return creator, self.service.publish(creator, draft.note_id)

    def plan(self, creator: str, note_id: str, *, price: str = "2.500000"):
        return self.service.create_subscription_plan(creator, {
            "title": "Research desk access",
            "description": "Time-limited access to the creator's subscriber-only research.",
            "duration_days": 7,
            "price": price,
            "note_ids": [note_id],
        })

    @staticmethod
    def receipt_for(intent, *, tx_hash: str):
        transfer = {
            "receiver_id": intent["recipient_account"],
            "amount": intent["amount_base_units"],
            "memo": intent["memo"],
        }
        args = base64.b64encode(json.dumps(transfer, separators=(",", ":")).encode()).decode()
        event = "EVENT_JSON:" + json.dumps({
            "standard": "nep141",
            "version": "1.0.0",
            "event": "ft_transfer",
            "data": [{
                "old_owner_id": intent["buyer_account"],
                "new_owner_id": intent["recipient_account"],
                "amount": intent["amount_base_units"],
            }],
        }, separators=(",", ":"))
        return {
            "status": {"SuccessReceiptId": f"receipt-{tx_hash}"},
            "transaction": {
                "hash": tx_hash,
                "signer_id": intent["buyer_account"],
                "receiver_id": intent["token_contract"],
                "actions": [{"FunctionCall": {"method_name": "ft_transfer", "args": args}}],
            },
            "receipts_outcome": [{
                "id": f"receipt-{tx_hash}",
                "block_hash": f"block-{tx_hash}",
                "outcome": {
                    "executor_id": intent["token_contract"],
                    "status": {"SuccessValue": ""},
                    "logs": [event],
                },
            }],
        }

    def verify(self, intent, tx_hash: str):
        self.reader.tx_result = self.receipt_for(intent, tx_hash=tx_hash)
        return self.service.verify_payment(self.auth_tokens[intent["buyer_account"]], intent["intent_id"], tx_hash)

    def test_plan_versions_are_owner_controlled_and_publicly_safe(self):
        creator, note = self.publish_note()
        plan = self.plan(creator, note.note_id)
        self.assertEqual(plan["terms_version"], 1)
        self.assertEqual(plan["duration_days"], 7)
        self.assertEqual(plan["subscriber_count"], 0)
        public = self.service.public_subscription_plan(plan["plan_id"])
        self.assertNotIn("version_history", public)
        self.assertNotIn("Private subscriber body", json.dumps(public))

        updated = self.service.update_subscription_plan(creator, plan["plan_id"], {
            "duration_days": 30,
            "price": "5.000000",
        })
        self.assertEqual(updated["terms_version"], 2)
        self.assertEqual(len(updated["version_history"]), 2)
        self.assertEqual(updated["version_history"][0]["price_base_units"], "2500000")
        self.assertEqual(updated["version_history"][1]["price_base_units"], "5000000")

        other = self.auth_token("other.testnet")
        with self.assertRaisesRegex(CreatorNotesError, "only the verified creator"):
            self.service.update_subscription_plan(other, plan["plan_id"], {"title": "Hijacked"})

    def test_verified_subscription_access_expiry_and_renewal(self):
        creator, note = self.publish_note()
        plan = self.plan(creator, note.note_id)
        buyer = self.auth_token("buyer.testnet")
        with self.assertRaisesRegex(CreatorNotesError, "verified purchase entitlement"):
            self.service.premium_content(buyer, note.note_id)

        intent = self.service.create_subscription_payment_intent(buyer, plan["plan_id"])
        self.assertEqual(intent["payment_kind"], "SUBSCRIPTION")
        self.assertEqual(intent["plan_id"], plan["plan_id"])
        self.assertEqual(intent["plan_version"], 1)
        self.assertEqual(intent["terms"]["duration_days"], 7)
        verified = self.verify(intent, "tx-sub-1")
        self.assertEqual(verified["status"], "VERIFIED")
        self.assertEqual(verified["subscription"]["status"], "ACTIVE")
        self.assertEqual(verified["subscription"]["plan_version"], 1)

        unlocked = self.service.premium_content(buyer, note.note_id)
        self.assertEqual(unlocked["access"], "subscription")
        self.assertEqual(unlocked["revision"], note.revision)
        original_expiry = verified["subscription"]["expires_at"]
        self.service.update_subscription_plan(creator, plan["plan_id"], {"price": "5.000000"})
        retained = self.service.subscriptions(buyer)["subscriber_subscriptions"][0]
        self.assertEqual(retained["plan_version"], 1)
        self.assertEqual(retained["price_base_units"], "2500000")

        duplicate = self.service.verify_payment(buyer, intent["intent_id"], "tx-sub-1")
        self.assertEqual(duplicate["subscription"]["expires_at"], original_expiry)
        self.assertEqual(len(self.store.list_subscription_payments(intent["subscription_id"])), 1)

        self.now[0] += timedelta(days=3)
        buyer = self.auth_token("buyer.testnet")
        renewal = self.service.create_subscription_payment_intent(buyer, plan["plan_id"])
        self.assertNotEqual(renewal["intent_id"], intent["intent_id"])
        self.assertEqual(renewal["plan_version"], 2)
        self.assertEqual(renewal["amount_base_units"], "5000000")
        renewed = self.verify(renewal, "tx-sub-2")
        self.assertEqual(renewed["subscription"]["status"], "ACTIVE")
        self.assertEqual(renewed["subscription"]["expires_at"], (NOW + timedelta(days=14)).isoformat().replace("+00:00", "Z"))
        self.assertEqual(len(renewed["subscription"]["payments"]), 2)

        self.now[0] = NOW + timedelta(days=14, microseconds=1)
        buyer = self.auth_token("buyer.testnet")
        with self.assertRaisesRegex(CreatorNotesError, "verified purchase entitlement"):
            self.service.premium_content(buyer, note.note_id)

    def test_cancel_keeps_paid_access_and_manual_renewal_reactivates(self):
        creator, note = self.publish_note()
        plan = self.plan(creator, note.note_id)
        buyer = self.auth_token("buyer.testnet")
        intent = self.service.create_subscription_payment_intent(buyer, plan["plan_id"])
        verified = self.verify(intent, "tx-cancel-1")
        cancelled = self.service.cancel_subscription(buyer, intent["subscription_id"])
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertTrue(cancelled["access_active"])
        self.assertEqual(cancelled["expires_at"], verified["subscription"]["expires_at"])
        self.assertEqual(self.service.premium_content(buyer, note.note_id)["access"], "subscription")

        renewal = self.service.create_subscription_payment_intent(buyer, plan["plan_id"])
        reactivated = self.verify(renewal, "tx-cancel-2")
        self.assertEqual(reactivated["subscription"]["status"], "ACTIVE")
        self.assertFalse(reactivated["subscription"]["renewal_cancelled"])

    def test_withdrawn_scope_denies_subscription_but_one_time_entitlement_survives(self):
        creator, note = self.publish_note()
        plan = self.plan(creator, note.note_id)
        buyer = self.auth_token("buyer.testnet")
        subscription_intent = self.service.create_subscription_payment_intent(buyer, plan["plan_id"])
        self.verify(subscription_intent, "tx-withdraw-sub")
        self.service.withdraw(creator, note.note_id, "scope withdrawn")
        with self.assertRaisesRegex(CreatorNotesError, "verified purchase entitlement"):
            self.service.premium_content(buyer, note.note_id)

        _, second = self.publish_note("One-time")
        one_time = self.service.create_payment_intent(buyer, second.note_id)
        self.verify(one_time, "tx-withdraw-one-time")
        self.service.withdraw(creator, second.note_id, "public withdrawal")
        self.assertEqual(self.service.premium_content(buyer, second.note_id)["access"], "purchased_revision")

    def test_concurrent_subscription_callbacks_credit_once(self):
        creator, note = self.publish_note()
        plan = self.plan(creator, note.note_id)
        buyer = self.auth_token("buyer.testnet")
        intent = self.service.create_subscription_payment_intent(buyer, plan["plan_id"])
        self.reader.tx_result = self.receipt_for(intent, tx_hash="tx-concurrent")
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.service.verify_payment(buyer, intent["intent_id"], "tx-concurrent"), range(4)))
        self.assertTrue(all(result["status"] == "VERIFIED" for result in results))
        self.assertEqual(len(self.store.list_subscription_payments(intent["subscription_id"])), 1)


if __name__ == "__main__":
    unittest.main()
