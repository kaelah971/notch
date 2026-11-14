"""Phase 8B1 HTTP boundary tests for premium research payments."""

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


class Phase8BApiTests(unittest.TestCase):
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
        return self.app.handle(method, path, {}, body, client="phase8b-test", headers=headers or {})

    def auth(self, account):
        status, result = self.call("POST", "/api/research/identity/challenge", {"account_id": account})
        self.assertEqual(status, 200)
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            status, result = self.call(
                "POST",
                "/api/research/identity/verify",
                {
                    "challenge_id": result["data"]["challenge_id"],
                    "account_id": account,
                    "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                    "signature": "fixture",
                },
            )
        self.assertEqual(status, 200)
        return result["data"]["session_token"]

    @staticmethod
    def receipt(intent):
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
            "status": {"SuccessReceiptId": "receipt-1"},
            "transaction": {
                "hash": "tx-api-1",
                "signer_id": intent["buyer_account"],
                "receiver_id": intent["token_contract"],
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

    def test_payout_intent_pending_verification_and_server_side_unlock(self):
        creator = self.auth("creator.testnet")
        status, payout = self.call("POST", "/api/research/payout/configure", {}, {"Authorization": f"Bearer {creator}"})
        self.assertEqual(status, 200)
        self.assertTrue(payout["data"]["configured"])

        body = {
            "title": "Premium Nvidia note",
            "thesis": "The public preview is evidence-backed and deliberately bounded.",
            "reference": {"kind": "topic", "id": "cand_test_nvidia", "label": "Nvidia"},
            "position": "NEUTRAL",
            "observation_cutoff": "2026-11-13T00:00:00Z",
            "supporting_evidence": [{
                "source_id": "wikimedia:en.wikipedia.org:Nvidia:2026-11-10",
                "url": "https://pageviews.wmcloud.org/",
                "observed_at": "2026-11-10T00:00:00Z",
                "claim": "The stored attention window is present.",
            }],
            "contradictory_evidence": [],
            "premium": {"enabled": True, "body": "Private method and assumptions.", "price": "1.500000"},
        }
        status, created = self.call("POST", "/api/research/notes", body, {"Authorization": f"Bearer {creator}"})
        self.assertEqual(status, 201)
        note_id = created["data"]["note_id"]
        status, published = self.call("POST", f"/api/research/notes/{note_id}/publish", {}, {"Authorization": f"Bearer {creator}"})
        self.assertEqual(status, 200)

        status, public = self.call("GET", f"/api/research/notes/{note_id}")
        self.assertEqual(status, 200)
        self.assertNotIn("body", public["data"]["premium"])
        self.assertNotIn("Private method", json.dumps(public))
        status, private_without_auth = self.call("GET", f"/api/research/notes/{note_id}/premium")
        self.assertEqual(status, 401)

        buyer = self.auth("buyer.testnet")
        auth = {"Authorization": f"Bearer {buyer}"}
        status, locked = self.call("GET", f"/api/research/notes/{note_id}/premium", headers=auth)
        self.assertEqual(status, 403)
        status, intent_response = self.call("POST", f"/api/research/notes/{note_id}/payment-intents", {}, auth)
        self.assertEqual(status, 201)
        intent = intent_response["data"]
        self.assertEqual(intent["network"], "testnet")
        self.assertEqual(intent["action"]["method_name"], "ft_transfer")
        self.reader.tx_result = {"status": {"Unknown": "pending"}}
        status, pending = self.call("POST", f"/api/research/payment-intents/{intent['intent_id']}/verify", {"tx_hash": "tx-api-1"}, auth)
        self.assertEqual(status, 202)
        self.assertEqual(pending["data"]["status"], "PENDING")
        self.reader.tx_result = self.receipt(intent)
        status, verified = self.call("POST", f"/api/research/payment-intents/{intent['intent_id']}/verify", {"tx_hash": "tx-api-1"}, auth)
        self.assertEqual(status, 200)
        self.assertEqual(verified["data"]["status"], "VERIFIED")
        status, unlocked = self.call("GET", f"/api/research/notes/{note_id}/premium", headers=auth)
        self.assertEqual(status, 200)
        self.assertEqual(unlocked["data"]["premium"]["body"], "Private method and assumptions.")
        status, purchases = self.call("GET", "/api/research/purchases", headers=auth)
        self.assertEqual(status, 200)
        self.assertEqual(len(purchases["data"]["buyer_entitlements"]), 1)
        status, revoked = self.call("POST", "/api/research/identity/revoke", {}, auth)
        self.assertEqual(status, 200)
        self.assertTrue(revoked["data"]["revoked"])
        status, _ = self.call("GET", "/api/research/purchases", headers=auth)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
