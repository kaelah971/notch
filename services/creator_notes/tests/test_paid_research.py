"""Phase 8B1 paid research unlock tests with explicitly mocked final receipts."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

from services.creator_notes.identity import CreatorIdentityService
from services.creator_notes.service import CreatorNotesError, CreatorNotesService
from services.creator_notes.store import CreatorNotesStore


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class FakeReader:
    def __init__(self):
        self.tx_result = None

    def view_access_key(self, account_id, public_key):
        return {"access_key": {"permission": "FullAccess"}}

    def transaction_status(self, tx_hash, signer_id):
        return self.tx_result

    def block_by_id(self, block_hash):
        return {"header": {"hash": block_hash, "height": 123}}


class FakeChain:
    def __init__(self):
        self.config = {"collateral_token": "usdc.tidepool-sandbox.testnet"}
        self.markets = {"market_1": {"market_id": "market_1", "source_id": "wikimedia-pageviews-v1"}}
        self.storage_registered = True
        self.token_balance = 10_000_000
        self.native_balance_value = 10**24

    def get_market(self, market_id):
        return self.markets.get(market_id)

    def get_candidate(self, candidate_id):
        if candidate_id != "cand_1":
            return None
        return {
            "candidate_id": candidate_id,
            "title": "Bitcoin",
            "discovery_signals": {"sources": ["wikimedia"], "settlement_article": "Bitcoin"},
            "settlement_coverage": {
                "source": "wikimedia-pageviews-v1",
                "article": "Bitcoin",
                "daily_views": [{"date": "2026-11-13", "views": 1000}],
            },
        }

    def ft_metadata(self, contract):
        return {"spec": "ft-1.0.0", "symbol": "TUSDC", "decimals": 6}

    def storage_balance(self, contract, account_id):
        return {"total": "1250000000000000000000", "available": "0"} if self.storage_registered else None

    def ft_balance(self, contract, account_id):
        return str(self.token_balance)

    def native_balance(self, account_id):
        return str(self.native_balance_value)


class PaidResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [NOW]
        self.reader = FakeReader()
        self.chain = FakeChain()
        self.store = CreatorNotesStore(f"{self.tmp.name}/creator.sqlite3")
        self.identity = CreatorIdentityService(store=self.store, reader=self.reader, clock=lambda: self.now[0])
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
        if self.service is not None:
            self.service.close()
        self.tmp.cleanup()

    def auth_token(self, account: str) -> str:
        challenge = self.service.challenge(account)
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            return self.service.verify_identity(
                {
                    "challenge_id": challenge["challenge_id"],
                    "account_id": account,
                    "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                    "signature": "fixture",
                }
            )["session_token"]

    def payload(self):
        return {
            "title": "Bitcoin attention premium note",
            "thesis": "The stored observation supports a bounded research case.",
            "reference": {"kind": "topic", "id": "cand_1", "label": "Bitcoin"},
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
                "body": "Private research body: assumptions, caveats, and the full method.",
                "price": "1.250000",
            },
        }

    def publish_note(self):
        creator = self.auth_token("creator.testnet")
        self.service.configure_payout(creator)
        draft = self.service.create_draft(creator, self.payload())
        published = self.service.publish(creator, draft.note_id)
        return creator, published

    @staticmethod
    def receipt_for(intent, *, amount=None, recipient=None, memo=None, status=None, tx_hash="tx-1", token_contract=None):
        transfer = {
            "receiver_id": recipient or intent["recipient_account"],
            "amount": amount or intent["amount_base_units"],
            "memo": memo or intent["memo"],
        }
        args = base64.b64encode(json.dumps(transfer, separators=(",", ":")).encode()).decode()
        event = "EVENT_JSON:" + json.dumps({
            "standard": "nep141",
            "version": "1.0.0",
            "event": "ft_transfer",
            "data": [{
                "old_owner_id": intent["buyer_account"],
                "new_owner_id": recipient or intent["recipient_account"],
                "amount": amount or intent["amount_base_units"],
            }],
        }, separators=(",", ":"))
        return {
            "status": status or {"SuccessReceiptId": "receipt-1"},
            "transaction": {
                "hash": tx_hash,
                "signer_id": intent["buyer_account"],
                "receiver_id": token_contract or intent["token_contract"],
                "actions": [{"FunctionCall": {"method_name": "ft_transfer", "args": args}}],
            },
            "receipts_outcome": [{
                "id": "receipt-1",
                "block_hash": "block-1",
                "outcome": {
                    "executor_id": intent["token_contract"],
                    "status": {"SuccessValue": ""},
                    "logs": [event],
                },
            }],
        }

    def test_public_preview_is_locked_and_verified_receipt_grants_exact_revision(self):
        creator, note = self.publish_note()
        public = self.service.public_detail(note.note_id)
        self.assertTrue(public["premium"]["enabled"])
        self.assertNotIn("body", public["premium"])
        self.assertNotIn("Private research body", json.dumps(public))
        buyer = self.auth_token("buyer.testnet")
        with self.assertRaisesRegex(CreatorNotesError, "verified purchase entitlement"):
            self.service.premium_content(buyer, note.note_id)
        intent = self.service.create_payment_intent(buyer, note.note_id)
        self.assertEqual(intent["amount_base_units"], "1250000")
        self.assertEqual(intent["action"]["method_name"], "ft_transfer")
        self.assertEqual(intent["action"]["attached_deposit_yocto"], "1")
        self.reader.tx_result = self.receipt_for(intent)
        verified = self.service.verify_payment(buyer, intent["intent_id"], "tx-1")
        self.assertEqual(verified["status"], "VERIFIED")
        replay_buyer = self.auth_token("replay-buyer.testnet")
        replay_intent = self.service.create_payment_intent(replay_buyer, note.note_id)
        replayed = self.service.verify_payment(replay_buyer, replay_intent["intent_id"], "tx-1")
        self.assertEqual(replayed["status"], "FAILED")
        self.assertEqual(replayed["failure_code"], "TX_ALREADY_USED")
        unlocked = self.service.premium_content(buyer, note.note_id)
        self.assertEqual(unlocked["revision"], note.revision)
        self.assertIn("Private research body", unlocked["premium"]["body"])
        self.assertEqual(self.service.premium_content(creator, note.note_id)["access"], "creator")

    def test_wrong_amount_and_failed_receipt_never_grant_access(self):
        _, note = self.publish_note()
        buyer = self.auth_token("buyer.testnet")
        intent = self.service.create_payment_intent(buyer, note.note_id)
        self.reader.tx_result = self.receipt_for(intent, amount="1")
        rejected = self.service.verify_payment(buyer, intent["intent_id"], "tx-1")
        self.assertEqual(rejected["status"], "FAILED")
        self.assertEqual(rejected["failure_code"], "AMOUNT_MISMATCH")
        with self.assertRaisesRegex(CreatorNotesError, "verified purchase entitlement"):
            self.service.premium_content(buyer, note.note_id)

        wrong_recipient = self.service.create_payment_intent(buyer, note.note_id)
        self.reader.tx_result = self.receipt_for(wrong_recipient, recipient="attacker.testnet", tx_hash="tx-recipient")
        rejected_recipient = self.service.verify_payment(buyer, wrong_recipient["intent_id"], "tx-recipient")
        self.assertEqual(rejected_recipient["failure_code"], "RECIPIENT_MISMATCH")

        wrong_memo = self.service.create_payment_intent(buyer, note.note_id)
        self.reader.tx_result = self.receipt_for(wrong_memo, memo="notch:forged", tx_hash="tx-memo")
        rejected_memo = self.service.verify_payment(buyer, wrong_memo["intent_id"], "tx-memo")
        self.assertEqual(rejected_memo["failure_code"], "MEMO_MISMATCH")

        wrong_token = self.service.create_payment_intent(buyer, note.note_id)
        self.reader.tx_result = self.receipt_for(wrong_token, tx_hash="tx-token", token_contract="fake-token.testnet")
        rejected_token = self.service.verify_payment(buyer, wrong_token["intent_id"], "tx-token")
        self.assertEqual(rejected_token["failure_code"], "TOKEN_CONTRACT_MISMATCH")

        second = self.service.create_payment_intent(buyer, note.note_id)
        self.reader.tx_result = self.receipt_for(second, status={"Failure": {"ActionError": {}}})
        failed = self.service.verify_payment(buyer, second["intent_id"], "tx-2")
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["failure_code"], "TRANSACTION_FAILED")

    def test_pending_finality_and_duplicate_verification_are_safe(self):
        _, note = self.publish_note()
        buyer = self.auth_token("buyer.testnet")
        intent = self.service.create_payment_intent(buyer, note.note_id)
        self.reader.tx_result = {"status": {"Unknown": "pending"}}
        pending = self.service.verify_payment(buyer, intent["intent_id"], "tx-pending")
        self.assertEqual(pending["status"], "PENDING")
        self.reader.tx_result = self.receipt_for(intent)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.service.verify_payment(buyer, intent["intent_id"], "tx-1"), range(4)))
        self.assertTrue(all(item["status"] == "VERIFIED" for item in results))
        self.assertEqual(len(self.store.list_entitlements(buyer_account="buyer.testnet")), 1)

    def test_buyer_must_have_token_and_gas_balance_before_intent(self):
        _, note = self.publish_note()
        buyer = self.auth_token("buyer.testnet")
        self.chain.token_balance = 1
        with self.assertRaisesRegex(CreatorNotesError, "does not have enough") as raised:
            self.service.create_payment_intent(buyer, note.note_id)
        self.assertEqual(raised.exception.code, "INSUFFICIENT_TOKEN_BALANCE")
        self.chain.token_balance = 10_000_000
        self.chain.native_balance_value = 0
        with self.assertRaisesRegex(CreatorNotesError, "positive NEAR") as raised:
            self.service.create_payment_intent(buyer, note.note_id)
        self.assertEqual(raised.exception.code, "INSUFFICIENT_GAS_BALANCE")

    def test_payout_requires_same_verified_account_and_registered_storage(self):
        creator = self.auth_token("creator.testnet")
        with self.assertRaisesRegex(CreatorNotesError, "must use the currently verified creator account"):
            self.service.configure_payout(creator, "other.testnet")
        self.chain.storage_registered = False
        with self.assertRaisesRegex(CreatorNotesError, "not registered"):
            self.service.configure_payout(creator)

    def test_price_precision_and_network_boundary_are_server_side(self):
        creator = self.auth_token("creator.testnet")
        with self.assertRaisesRegex(CreatorNotesError, "more than 6"):
            bad = self.payload()
            bad["premium"]["price"] = "0.0000001"
            self.service.create_draft(creator, bad)
        self.service.payment_network = "mainnet"
        with self.assertRaisesRegex(CreatorNotesError, "restricted"):
            self.service.configure_payout(creator)

    def test_entitlement_survives_service_reload(self):
        creator, note = self.publish_note()
        buyer = self.auth_token("buyer.testnet")
        intent = self.service.create_payment_intent(buyer, note.note_id)
        self.reader.tx_result = self.receipt_for(intent)
        self.service.verify_payment(buyer, intent["intent_id"], "tx-1")
        self.service.close()
        self.service = None
        store = CreatorNotesStore(f"{self.tmp.name}/creator.sqlite3")
        identity = CreatorIdentityService(store=store, reader=self.reader, clock=lambda: self.now[0])
        reloaded = CreatorNotesService(
            store=store, reader=self.reader, chain=self.chain, radar=self.chain,
            identity=identity, payment_token="usdc.tidepool-sandbox.testnet", clock=lambda: self.now[0],
        )
        try:
            self.assertIn("Private research body", reloaded.premium_content(buyer, note.note_id)["premium"]["body"])
            self.assertEqual(len(reloaded.purchases(buyer)["buyer_entitlements"]), 1)
        finally:
            reloaded.close()


if __name__ == "__main__":
    unittest.main()
