"""Private Research Vault owner-boundary tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from services.creator_notes.identity import CreatorIdentityService
from services.creator_notes.service import CreatorNotesError, CreatorNotesService
from services.creator_notes.store import CreatorNotesStore


class FakeReader:
    def view_access_key(self, account_id, public_key):
        return {"access_key": {"permission": "FullAccess"}}


class FakeChain:
    def get_market(self, market_id):
        if market_id != "market_1":
            return None
        return {
            "market_id": market_id,
            "question": "FORECAST: private vault test",
            "status": "open",
            "entries_open": True,
            "winning_choice": None,
            "close_at": "1794477000000000000",
            "resolve_after": "1794563400000000000",
            "resolved_at": None,
        }


class FakeRadar:
    def get_candidate(self, candidate_id):
        return None


class PrivateVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = f"{self.tmp.name}/creator.sqlite3"
        self.now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.store = CreatorNotesStore(self.path)
        self.identity = CreatorIdentityService(store=self.store, reader=FakeReader(), clock=lambda: self.now)
        self.service = CreatorNotesService(
            store=self.store,
            reader=FakeReader(),
            chain=FakeChain(),
            radar=FakeRadar(),
            identity=self.identity,
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def auth_token(self, account: str) -> str:
        challenge = self.service.challenge(account)
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            result = self.service.verify_identity(
                {
                    "challenge_id": challenge["challenge_id"],
                    "account_id": account,
                    "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                    "signature": "fixture",
                }
            )
        return result["session_token"]

    @staticmethod
    def payload():
        return {
            "market_id": "market_1",
            "title": "Bitcoin attention thesis",
            "thesis": "The source-backed attention signal is worth revisiting before the market closes.",
            "predicted_outcome": "UP",
            "confidence": 72,
            "source_references": ["market:market_1:rule", "https://example.invalid/source"],
            "invalidation_condition": "Invalidate if the next complete observation window reverses the signal.",
        }

    def test_owner_crud_and_persistence_survive_store_restart(self):
        token = self.auth_token("alice.testnet")
        created = self.service.private_research_create(token, self.payload())
        self.assertEqual(created["visibility"], "PRIVATE")
        self.assertEqual(created["owner_account"], "alice.testnet")
        self.assertEqual(created["market"]["status"], "open")
        self.assertEqual(len(self.service.private_research_mine(token)), 1)

        self.service.close()
        self.store = CreatorNotesStore(self.path)
        self.identity = CreatorIdentityService(store=self.store, reader=FakeReader(), clock=lambda: self.now)
        self.service = CreatorNotesService(
            store=self.store,
            reader=FakeReader(),
            chain=FakeChain(),
            radar=FakeRadar(),
            identity=self.identity,
            clock=lambda: self.now,
        )
        reopened = self.service.private_research_get(token, created["research_id"])
        self.assertEqual(reopened["thesis"], self.payload()["thesis"])

        updated = self.service.private_research_update(
            token,
            created["research_id"],
            {"confidence": 80, "invalidation_condition": "Invalidate on a confirmed reversal."},
        )
        self.assertEqual(updated["confidence"], 80.0)
        self.assertEqual(updated["invalidation_condition"], "Invalidate on a confirmed reversal.")
        deleted = self.service.private_research_delete(token, created["research_id"])
        self.assertTrue(deleted["deleted"])
        self.assertEqual(self.service.private_research_mine(token), [])

    def test_auth_and_cross_wallet_access_are_owner_bound_and_non_enumerating(self):
        with self.assertRaisesRegex(CreatorNotesError, "session"):
            self.service.private_research_mine(None)
        alice = self.auth_token("alice.testnet")
        bob = self.auth_token("bob.testnet")
        created = self.service.private_research_create(alice, self.payload())

        self.assertEqual(self.service.private_research_mine(bob), [])
        for operation in (
            lambda: self.service.private_research_get(bob, created["research_id"]),
            lambda: self.service.private_research_update(bob, created["research_id"], {"title": "takeover"}),
            lambda: self.service.private_research_delete(bob, created["research_id"]),
        ):
            with self.assertRaisesRegex(CreatorNotesError, "private research was not found"):
                operation()
        with self.assertRaisesRegex(CreatorNotesError, "ownership and visibility"):
            self.service.private_research_create(alice, {**self.payload(), "owner_account": "bob.testnet"})
        with self.assertRaisesRegex(CreatorNotesError, "ownership and visibility"):
            self.service.private_research_update(alice, created["research_id"], {"owner": "bob.testnet"})

    def test_private_records_do_not_enter_public_creator_research(self):
        token = self.auth_token("alice.testnet")
        self.service.private_research_create(token, self.payload())
        self.assertEqual(self.service.public_list(), [])


if __name__ == "__main__":
    unittest.main()
