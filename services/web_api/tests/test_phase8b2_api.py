"""Phase 8B2 HTTP boundary tests for subscription plans and access."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from services.creator_notes.identity import CreatorIdentityService
from services.creator_notes.service import CreatorNotesService
from services.creator_notes.store import CreatorNotesStore
from services.web_api.tests.test_api import make_app


class Phase8B2ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = make_app()
        self.app.chain.ft_metadata = lambda contract: {"spec": "ft-1.0.0", "symbol": "TUSDC", "decimals": 6}
        self.app.chain.storage_balance = lambda contract, account_id: {"total": "1", "available": "0"}
        reader = type("Reader", (), {})()
        reader.view_access_key = lambda account_id, public_key: {"access_key": {"permission": "FullAccess"}}
        reader.tx_result = None
        reader.transaction_status = lambda tx_hash, signer_id: reader.tx_result
        reader.block_by_id = lambda block_hash: {"header": {"hash": block_hash, "height": 123}}
        clock = lambda: datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        store = CreatorNotesStore(f"{self.tmp.name}/creator.sqlite3")
        identity = CreatorIdentityService(store=store, reader=reader, clock=clock)
        self.reader = reader
        self.app.creator_notes_service = CreatorNotesService(
            store=store,
            reader=reader,
            chain=self.app.chain,
            radar=self.app.radar,
            identity=identity,
            payment_token="usdc.tidepool-sandbox.testnet",
            clock=clock,
        )

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, headers=None):
        return self.app.handle(method, path, {}, body, client="phase8b2-test", headers=headers or {})

    def auth(self, account):
        status, result = self.call("POST", "/api/research/identity/challenge", {"account_id": account})
        self.assertEqual(status, 200)
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            status, result = self.call("POST", "/api/research/identity/verify", {
                "challenge_id": result["data"]["challenge_id"],
                "account_id": account,
                "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                "signature": "fixture",
            })
        self.assertEqual(status, 200)
        return result["data"]["session_token"]

    @staticmethod
    def receipt(intent):
        transfer = {"receiver_id": intent["recipient_account"], "amount": intent["amount_base_units"], "memo": intent["memo"]}
        args = base64.b64encode(json.dumps(transfer, separators=(",", ":")).encode()).decode()
        event = "EVENT_JSON:" + json.dumps({
            "standard": "nep141", "version": "1.0.0", "event": "ft_transfer",
            "data": [{"old_owner_id": intent["buyer_account"], "new_owner_id": intent["recipient_account"], "amount": intent["amount_base_units"]}],
        }, separators=(",", ":"))
        return {
            "status": {"SuccessReceiptId": "receipt-sub"},
            "transaction": {
                "hash": "tx-sub-api",
                "signer_id": intent["buyer_account"],
                "receiver_id": intent["token_contract"],
                "actions": [{"FunctionCall": {"method_name": "ft_transfer", "args": args}}],
            },
            "receipts_outcome": [{
                "id": "receipt-sub", "block_hash": "block-sub",
                "outcome": {"executor_id": intent["token_contract"], "status": {"SuccessValue": ""}, "logs": [event]},
            }],
        }

    def test_http_subscription_plan_payment_access_and_cancel(self):
        creator = self.auth("creator.testnet")
        status, payout = self.call("POST", "/api/research/payout/configure", {}, {"Authorization": f"Bearer {creator}"})
        self.assertEqual(status, 200)
        self.assertTrue(payout["data"]["configured"])
        note_body = {
            "title": "Subscriber note",
            "thesis": "A bounded source-backed thesis.",
            "reference": {"kind": "topic", "id": "cand_test_nvidia", "label": "Nvidia"},
            "position": "NEUTRAL",
            "observation_cutoff": "2026-11-13T00:00:00Z",
            "supporting_evidence": [{"source_id": "wikimedia:en.wikipedia.org:Nvidia:2026-11-10", "url": "https://pageviews.wmcloud.org/", "observed_at": "2026-11-10T00:00:00Z", "claim": "The stored observation is present."}],
            "contradictory_evidence": [],
            "premium": {"enabled": True, "body": "Subscriber-only method.", "price": "1.500000"},
        }
        status, created = self.call("POST", "/api/research/notes", note_body, {"Authorization": f"Bearer {creator}"})
        self.assertEqual(status, 201)
        note_id = created["data"]["note_id"]
        status, _ = self.call("POST", f"/api/research/notes/{note_id}/publish", {}, {"Authorization": f"Bearer {creator}"})
        self.assertEqual(status, 200)
        status, plan_response = self.call("POST", "/api/research/plans", {
            "title": "Nvidia desk",
            "description": "Seven days of subscriber-only research.",
            "duration_days": 7,
            "price": "2.500000",
            "note_ids": [note_id],
        }, {"Authorization": f"Bearer {creator}"})
        self.assertEqual(status, 201)
        plan = plan_response["data"]
        self.assertEqual(plan["terms_version"], 1)
        status, public = self.call("GET", f"/api/research/plans/{plan['plan_id']}")
        self.assertEqual(status, 200)
        self.assertNotIn("Subscriber-only method", json.dumps(public))
        status, _ = self.call("POST", f"/api/research/plans/{plan['plan_id']}/update", {"title": "Hijack"}, {"Authorization": f"Bearer {self.auth('other.testnet')}"})
        self.assertEqual(status, 403)

        buyer = self.auth("buyer.testnet")
        auth = {"Authorization": f"Bearer {buyer}"}
        status, locked = self.call("GET", f"/api/research/notes/{note_id}/premium", headers=auth)
        self.assertEqual(status, 403)
        status, intent_response = self.call("POST", f"/api/research/plans/{plan['plan_id']}/payment-intents", {}, auth)
        self.assertEqual(status, 201)
        intent = intent_response["data"]
        self.assertEqual(intent["payment_kind"], "SUBSCRIPTION")
        self.reader.tx_result = self.receipt(intent)
        status, verified = self.call("POST", f"/api/research/payment-intents/{intent['intent_id']}/verify", {"tx_hash": "tx-sub-api"}, auth)
        self.assertEqual(status, 200)
        self.assertEqual(verified["data"]["status"], "VERIFIED")
        status, unlocked = self.call("GET", f"/api/research/notes/{note_id}/premium", headers=auth)
        self.assertEqual(status, 200)
        self.assertEqual(unlocked["data"]["access"], "subscription")
        status, subscriptions = self.call("GET", "/api/research/subscriptions", headers=auth)
        self.assertEqual(status, 200)
        self.assertEqual(subscriptions["data"]["subscriber_subscriptions"][0]["status"], "ACTIVE")
        subscription_id = subscriptions["data"]["subscriber_subscriptions"][0]["subscription_id"]
        status, cancelled = self.call("POST", f"/api/research/subscriptions/{subscription_id}/cancel", {}, auth)
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["data"]["status"], "CANCELLED")
        self.assertTrue(cancelled["data"]["access_active"])


if __name__ == "__main__":
    unittest.main()
