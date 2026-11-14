"""Phase 8A creator-note lifecycle and ownership boundary tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.creator_notes.identity import CreatorIdentityService, verify_nep413_signature
from services.creator_notes.service import CreatorNotesError, CreatorNotesService
from services.creator_notes.store import CreatorNotesStore


class FakeReader:
    def view_access_key(self, account_id, public_key):
        return {"access_key": {"permission": "FullAccess"}}


class FakeChain:
    def get_market(self, market_id):
        return {"market_id": market_id} if market_id == "market_1" else None


class FakeRadar:
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


class CreatorNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.store = CreatorNotesStore(f"{self.tmp.name}/creator.sqlite3")
        self.identity = CreatorIdentityService(
            store=self.store,
            reader=FakeReader(),
            clock=lambda: self.now,
        )
        self.service = CreatorNotesService(
            store=self.store,
            reader=FakeReader(),
            chain=FakeChain(),
            radar=FakeRadar(),
            identity=self.identity,
            clock=lambda: self.now,
        )
        self.account = "creator.testnet"

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def auth_token(self):
        challenge = self.service.challenge(self.account)
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            result = self.service.verify_identity(
                {
                    "challenge_id": challenge["challenge_id"],
                    "account_id": self.account,
                    "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                    "signature": "not-used-by-patched-vector",
                }
            )
        return result["session_token"]

    def payload(self):
        return {
            "title": "Bitcoin attention has a source-bounded upward case",
            "thesis": "The observed attention movement is notable, but this note does not claim a price forecast.",
            "reference": {"kind": "topic", "id": "cand_1", "label": "Bitcoin"},
            "position": "UP",
            "observation_cutoff": "2026-11-13T12:00:00Z",
            "supporting_evidence": [
                {
                    "source_id": "wikimedia:en.wikipedia.org:Bitcoin:2026-11-13",
                    "url": "https://pageviews.wmcloud.org/",
                    "observed_at": "2026-11-13T00:00:00Z",
                    "claim": "The stored Wikimedia observation window shows elevated attention.",
                }
            ],
            "contradictory_evidence": [],
            "strategy_reference": {
                "id": "strategy_local_1",
                "revision_hash": "sha256:" + "a" * 64,
            },
            "evaluation_reference": None,
        }

    def test_nep413_signature_vector_verifies_without_wallet_or_chain_side_effects(self):
        self.assertTrue(
            verify_nep413_signature(
                public_key="ed25519:29UWYCdxGPfvc24jMi8M5jqLAdGQk5q4eA49oMMCvSwa",
                signature_b64="oCxet4wCap4nfHAqGmWzh8km8sGzODiZNhdBXG6DNzuVX8Sykm8DR7WInKTz+gMe/BT4k7VR6EE/v+jS9uxbDA==",
                message="Notch Creator Studio ownership challenge\nAccount: creator.testnet\nNonce: AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=\nExpires: 2026-11-14T12:10:00Z",
                nonce_b64="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
                recipient="notch.creator",
            )
        )

    def test_verified_challenge_is_single_use_and_session_is_opaque(self):
        challenge = self.service.challenge(self.account)
        with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
            verified = self.service.verify_identity(
                {
                    "challenge_id": challenge["challenge_id"],
                    "account_id": self.account,
                    "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                    "signature": "fixture",
                }
            )
        self.assertTrue(verified["verified"])
        self.assertNotIn("fixture", verified["session_token"])
        with self.assertRaisesRegex(Exception, "already been used"):
            with patch("services.creator_notes.identity.verify_nep413_signature", return_value=True):
                self.service.verify_identity(
                    {
                        "challenge_id": challenge["challenge_id"],
                        "account_id": self.account,
                        "public_key": "ed25519:1111111111111111111111111111111111111111111111111111",
                        "signature": "fixture",
                    }
                )

    def test_session_revocation_is_server_side_and_single_use(self):
        token = self.auth_token()
        self.assertEqual(self.identity.session(token)["account_id"], self.account)
        revoked = self.service.revoke_identity(token)
        self.assertTrue(revoked["revoked"])
        with self.assertRaisesRegex(CreatorNotesError, "revoked"):
            self.service.mine(token)

    def test_session_expiry_blocks_private_access(self):
        token = self.auth_token()
        self.now = self.now + timedelta(days=2)
        with self.assertRaisesRegex(CreatorNotesError, "expired"):
            self.service.mine(token)

    def test_network_binding_is_part_of_the_challenge_and_session(self):
        identity = CreatorIdentityService(store=self.store, reader=FakeReader(), network="mainnet", clock=lambda: self.now)
        with self.assertRaisesRegex(Exception, "Testnet"):
            identity.create_challenge(self.account)

    def test_publish_exposes_provenance_and_preserves_strategy_revision(self):
        token = self.auth_token()
        draft = self.service.create_draft(token, self.payload())
        published = self.service.publish(token, draft.note_id)
        self.assertEqual(published.status, "PUBLISHED")
        self.assertEqual(published.source_ids, ["wikimedia:en.wikipedia.org:Bitcoin:2026-11-13"])
        public = self.service.public_detail(draft.note_id)
        self.assertEqual(public["content_digest"], published.content_digest)
        self.assertEqual(public["strategy_reference"]["revision_hash"], "sha256:" + "a" * 64)
        self.assertEqual(len(public["revision_history"]), 2)
        self.assertEqual(public["revision_history"][0]["status"], "DRAFT")

    def test_duplicate_publication_and_withdrawal_are_explicit(self):
        token = self.auth_token()
        first = self.service.create_draft(token, self.payload())
        self.service.publish(token, first.note_id)
        duplicate = self.service.create_draft(token, self.payload())
        with self.assertRaisesRegex(CreatorNotesError, "same note revision"):
            self.service.publish(token, duplicate.note_id)
        withdrawn = self.service.withdraw(token, first.note_id, "source review requested")
        self.assertEqual(withdrawn.status, "WITHDRAWN")
        with self.assertRaisesRegex(CreatorNotesError, "published research note was not found"):
            self.service.public_detail(first.note_id)

    def test_future_evidence_is_rejected_without_lookahead(self):
        token = self.auth_token()
        payload = self.payload()
        payload["supporting_evidence"][0]["observed_at"] = "2026-11-14T12:00:01Z"
        with self.assertRaisesRegex(CreatorNotesError, "after the note cutoff"):
            self.service.create_draft(token, payload)

    def test_unparseable_timestamps_are_validation_errors(self):
        token = self.auth_token()
        payload = self.payload()
        payload["observation_cutoff"] = "not-a-timestamp"
        with self.assertRaisesRegex(CreatorNotesError, "observation_cutoff must be an ISO-8601 timestamp"):
            self.service.create_draft(token, payload)

    def test_unstored_wikimedia_observation_is_rejected(self):
        token = self.auth_token()
        payload = self.payload()
        payload["supporting_evidence"][0]["source_id"] = "wikimedia:en.wikipedia.org:Bitcoin:2026-11-12"
        with self.assertRaisesRegex(CreatorNotesError, "not present in the referenced Wikimedia observation"):
            self.service.create_draft(token, payload)

    def test_non_owner_cannot_edit(self):
        token = self.auth_token()
        draft = self.service.create_draft(token, self.payload())
        other = self.store.create_session(
            account_id="other.testnet",
            public_key="ed25519:1111111111111111111111111111111111111111111111111111",
            created_at="2026-11-14T12:00:00Z",
            expires_at="2026-11-15T12:00:00Z",
        )
        with self.assertRaisesRegex(CreatorNotesError, "only the verified creator"):
            self.service.update(other, draft.note_id, {"title": "takeover"})


if __name__ == "__main__":
    unittest.main()
