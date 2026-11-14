"""Private Research Vault HTTP boundary tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import urlparse

from services.creator_notes.identity import CreatorIdentityService
from services.creator_notes.service import CreatorNotesService
from services.creator_notes.store import CreatorNotesStore
from services.creator_notes.tests.test_private_vault import FakeChain, FakeRadar, FakeReader
from services.web_api.tests.test_api import make_app


class PrivateVaultAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.store = CreatorNotesStore(f"{self.tmp.name}/creator.sqlite3")
        self.identity = CreatorIdentityService(store=self.store, reader=FakeReader(), clock=lambda: self.now)
        self.service = CreatorNotesService(
            store=self.store,
            reader=FakeReader(),
            chain=FakeChain(),
            radar=FakeRadar(),
            identity=self.identity,
            clock=lambda: self.now,
        )
        self.app = make_app()
        self.app.creator_notes_service = self.service

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def token(self, account: str) -> str:
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

    @staticmethod
    def payload():
        return {
            "market_id": "market_1",
            "title": "Private API thesis",
            "thesis": "Keep this content owner-restricted.",
            "predicted_outcome": "NEUTRAL",
            "confidence": 55,
            "source_references": ["market:market_1:rule"],
            "invalidation_condition": "A verified contrary observation invalidates this thesis.",
        }

    def call(self, method: str, path: str, body=None, token: str | None = None):
        parsed = urlparse(path)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.app.handle(method, parsed.path, {}, body, headers=headers)

    def test_route_requires_session_and_owner_b_cannot_enumerate_or_mutate(self):
        status, payload = self.call("GET", "/api/research/vault")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["code"], "AUTH_REQUIRED")

        alice = self.token("alice.testnet")
        bob = self.token("bob.testnet")
        status, created = self.call("POST", "/api/research/vault", self.payload(), alice)
        self.assertEqual(status, 201)
        research_id = created["data"]["research_id"]

        status, public = self.call("GET", "/api/research/notes")
        self.assertEqual(status, 200)
        self.assertEqual(public["data"], [])

        status, mine = self.call("GET", "/api/research/vault", token=bob)
        self.assertEqual(status, 200)
        self.assertEqual(mine["data"], [])
        status, hidden = self.call("GET", f"/api/research/vault/{research_id}", token=bob)
        self.assertEqual(status, 404)
        self.assertEqual(hidden["error"]["code"], "PRIVATE_RESEARCH_NOT_FOUND")
        status, hidden_update = self.call(
            "POST", f"/api/research/vault/{research_id}/update", {"title": "takeover"}, bob
        )
        self.assertEqual(status, 404)
        self.assertEqual(hidden_update["error"]["code"], "PRIVATE_RESEARCH_NOT_FOUND")

        status, spoofed = self.call(
            "POST", "/api/research/vault", {**self.payload(), "owner_account": "bob.testnet"}, alice
        )
        self.assertEqual(status, 403)
        self.assertEqual(spoofed["error"]["code"], "PRIVATE_RESEARCH_OWNER_IMMUTABLE")

        status, deleted = self.call("POST", f"/api/research/vault/{research_id}/delete", {}, alice)
        self.assertEqual(status, 200)
        self.assertTrue(deleted["data"]["deleted"])


if __name__ == "__main__":
    unittest.main()
