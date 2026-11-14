"""Focused tests for finalized, wallet-scoped notification reconciliation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services.creator_notes.identity import CreatorIdentityError
from services.web_api.notifications import NotificationService, NotificationStore
from services.web_api.tests.test_api import make_app


ACCOUNT_A = "alice.testnet"
ACCOUNT_B = "bob.testnet"


class FakeFinalChain:
    def __init__(self) -> None:
        self.state_changes = 0
        self.markets = [
            self._market("resolved-claim", "resolved", "winning_outcome", 0),
            self._market("resolved-zero", "resolved", "winning_outcome", 1),
            self._market("void-refund", "voided", "void", None),
            self._market("still-open", "open", None, None),
            self._market("invalid-resolution", "resolved", "winning_outcome", None),
            self._market("unfinalized", "resolved", "winning_outcome", 0),
        ]

    @staticmethod
    def _market(market_id: str, status: str, resolution_kind: str | None, winner: int | None) -> dict:
        return {
            "market_id": market_id,
            "mode": "trend_trading",
            "question": f"test market {market_id}",
            "choices": ["UP", "DOWN"],
            "status": status,
            "winning_outcome": winner,
            "winning_choice": ["UP", "DOWN"][winner] if winner in (0, 1) else None,
            "resolution_kind": resolution_kind,
            "resolved_at": "2026-11-12T04:00:29Z" if status != "open" else None,
        }

    def list_markets(self):
        return list(self.markets)

    def get_finalized_market_position(self, market_id: str, account_id: str):
        market = next(item for item in self.markets if item["market_id"] == market_id)
        if market_id == "still-open":
            position = self._position(market_id, account_id, "0", "0", "open")
        elif market_id == "resolved-claim" and account_id == ACCOUNT_A:
            position = self._position(market_id, account_id, "100", "100", "claimable")
        elif market_id == "resolved-zero" and account_id == ACCOUNT_A:
            position = self._position(market_id, account_id, "100", "0", "claimed")
        elif market_id == "void-refund" and account_id == ACCOUNT_A:
            position = self._position(market_id, account_id, "100", "100", "claimable")
        elif market_id == "invalid-resolution" and account_id == ACCOUNT_A:
            position = self._position(market_id, account_id, "100", "100", "claimable")
        elif market_id == "unfinalized" and account_id == ACCOUNT_A:
            position = self._position(market_id, account_id, "100", "100", "claimable")
        else:
            position = None
        finality = "optimistic" if market_id == "unfinalized" else "final"
        return market, position, {
            "finality": finality,
            "rpc_source": "fake-final-rpc",
            "market_block_height": 100,
            "market_block_hash": f"block-{market_id}",
            "position_block_height": 101,
            "position_block_hash": f"position-{market_id}",
        }

    @staticmethod
    def _position(market_id: str, account_id: str, claimable: str, pending: str, state: str):
        return {
            "market_id": market_id,
            "account_id": account_id,
            "stakes": ["100", "0"],
            "total_stake": "100",
            "claimed_total": "0" if state != "claimed" else "100",
            "pending_amount": pending,
            "claimable": claimable,
            "claim_state": state,
        }


class NotificationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = NotificationStore(Path(self.temp.name) / "notifications.sqlite3")
        self.service = NotificationService(
            store=self.store,
            chain=FakeFinalChain(),
            clock=lambda: datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_finalized_resolution_claim_refund_and_open_guards(self):
        result = self.service.reconcile(ACCOUNT_A)
        self.assertEqual(result["finality"], "final")
        self.assertEqual(result["created"], 4)
        rows = self.store.list_for_account(ACCOUNT_A)
        self.assertEqual({row["type"] for row in rows}, {"MARKET_RESOLVED", "CLAIM_READY", "REFUND_READY"})
        self.assertEqual(sum(row["type"] == "MARKET_RESOLVED" for row in rows), 2)
        self.assertEqual(sum(row["type"] == "CLAIM_READY" for row in rows), 1)
        self.assertEqual(sum(row["type"] == "REFUND_READY" for row in rows), 1)
        self.assertNotIn("still-open", {row["market_id"] for row in rows})
        self.assertNotIn("invalid-resolution", {row["market_id"] for row in rows})
        self.assertNotIn("unfinalized", {row["market_id"] for row in rows})
        self.assertTrue(all(row["provenance"]["finality"] == "final" for row in rows))

    def test_reconciliation_is_idempotent_and_read_only(self):
        first = self.service.reconcile(ACCOUNT_A)
        second = self.service.reconcile(ACCOUNT_A)
        self.assertEqual(first["created"], 4)
        self.assertEqual(second["created"], 0)
        self.assertEqual(self.store.unread_count(ACCOUNT_A), 4)
        self.assertEqual(self.service.chain.state_changes, 0)

    def test_read_state_persists_and_wallets_are_isolated(self):
        self.service.reconcile(ACCOUNT_A)
        rows_a = self.store.list_for_account(ACCOUNT_A)
        self.assertEqual(len(rows_a), 4)
        self.assertEqual(self.store.list_for_account(ACCOUNT_B), [])
        self.assertTrue(self.service.mark_read(ACCOUNT_A, rows_a[0]["notification_id"]))
        self.assertFalse(self.store.list_for_account(ACCOUNT_A)[0]["unread"])
        self.assertFalse(self.service.mark_read(ACCOUNT_B, rows_a[0]["notification_id"]))
        self.assertEqual(self.store.unread_count(ACCOUNT_A), 3)

        reopened = NotificationStore(Path(self.temp.name) / "notifications.sqlite3")
        try:
            persisted = reopened.list_for_account(ACCOUNT_A)
            self.assertEqual(len(persisted), 4)
            self.assertEqual(sum(row["unread"] for row in persisted), 3)
        finally:
            reopened.close()


class NotificationAuthAPITests(unittest.TestCase):
    class Identity:
        def session(self, token):
            if token == "token-a":
                return {"account_id": ACCOUNT_A}
            if token == "token-b":
                return {"account_id": ACCOUNT_B}
            raise CreatorIdentityError("AUTH_REQUIRED", "session required", status=401)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = NotificationStore(Path(self.temp.name) / "notifications.sqlite3")
        self.service = NotificationService(store=self.store, chain=FakeFinalChain())
        self.app = make_app()
        self.app.notifications = self.service
        self.app.creator_notes_service = SimpleNamespace(identity=self.Identity(), close=lambda: None)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_inbox_requires_session_and_is_not_account_selectable(self):
        status, payload = self.app.handle("GET", "/api/notifications", {}, None, headers={})
        self.assertEqual(status, 401)
        self.service.reconcile(ACCOUNT_A)
        status, payload = self.app.handle(
            "GET", "/api/notifications", {}, None,
            headers={"Authorization": "Bearer token-b"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"], [])
        self.assertEqual(payload["meta"]["unread_count"], 0)

    def test_read_endpoint_cannot_cross_wallet_boundary(self):
        self.service.reconcile(ACCOUNT_A)
        row = self.store.list_for_account(ACCOUNT_A)[0]
        status, _ = self.app.handle(
            "POST", f"/api/notifications/{row['notification_id']}/read", {}, {},
            headers={"Authorization": "Bearer token-b"},
        )
        self.assertEqual(status, 404)
        self.assertTrue(self.store.list_for_account(ACCOUNT_A)[0]["unread"])


if __name__ == "__main__":
    unittest.main()
