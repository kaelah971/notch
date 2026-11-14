"""Phase 8A API boundary tests for verified creator publishing."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from services.creator_notes.identity import CreatorIdentityService
from services.creator_notes.service import CreatorNotesService
from services.creator_notes.store import CreatorNotesStore
from services.web_api.tests.test_api import make_app


class FakeIdentityReader:
    def view_access_key(self, account_id, public_key):
        return {"access_key": {"permission": "FullAccess"}}


class Phase8AApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = make_app()
        store = CreatorNotesStore(f"{self.tmp.name}/creator.sqlite3")
        reader = FakeIdentityReader()
        clock = lambda: datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        identity = CreatorIdentityService(store=store, reader=reader, clock=clock)
        self.app.creator_notes_service = CreatorNotesService(
            store=store,
            reader=reader,
            chain=self.app.chain,
            radar=self.app.radar,
            identity=identity,
            clock=clock,
        )

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, headers=None):
        return self.app.handle(method, path, {}, body, client="phase8a-test", headers=headers or {})

    def test_challenge_publish_discovery_and_auth_boundary(self):
        account = "creator.testnet"
        status, challenge_payload = self.call(
            "POST", "/api/research/identity/challenge", {"account_id": account}
        )
        self.assertEqual(status, 200)
        challenge = challenge_payload["data"]
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            status, verified_payload = self.call(
                "POST",
                "/api/research/identity/verify",
                {
                    "challenge_id": challenge["challenge_id"],
                    "account_id": account,
                    "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                    "signature": "fixture",
                },
            )
        self.assertEqual(status, 200)
        token = verified_payload["data"]["session_token"]
        body = {
            "title": "Nvidia attention note",
            "thesis": "Stored attention evidence is notable, without claiming a price outcome.",
            "reference": {"kind": "topic", "id": "cand_test_nvidia", "label": "Nvidia"},
            "position": "NEUTRAL",
            "observation_cutoff": "2026-11-13T00:00:00Z",
            "supporting_evidence": [{
                "source_id": "wikimedia:en.wikipedia.org:Nvidia:2026-11-10",
                "url": "https://pageviews.wmcloud.org/",
                "observed_at": "2026-11-10T00:00:00Z",
                "claim": "The source-backed observation is present in the stored window.",
            }],
            "contradictory_evidence": [],
        }
        headers = {"Authorization": f"Bearer {token}"}
        status, created = self.call("POST", "/api/research/notes", body, headers)
        self.assertEqual(status, 201)
        note_id = created["data"]["note_id"]
        status, _ = self.call("GET", "/api/research/notes/mine", headers=headers)
        self.assertEqual(status, 200)
        status, published = self.call(
            "POST", f"/api/research/notes/{note_id}/publish", {}, headers
        )
        self.assertEqual(status, 200)
        self.assertEqual(published["data"]["status"], "PUBLISHED")
        status, public = self.call("GET", "/api/research/notes")
        self.assertEqual(status, 200)
        self.assertEqual(public["data"][0]["note_id"], note_id)
        status, private_without_auth = self.call("GET", "/api/research/notes/mine")
        self.assertEqual(status, 401)
        self.assertEqual(private_without_auth["error"]["code"], "AUTH_REQUIRED")


if __name__ == "__main__":
    unittest.main()
