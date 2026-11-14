"""Phase 7B HTTP boundary tests: explicit live quotes and submitted hashes only."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.web_api.tests.test_api import make_app


class Prepared:
    def __init__(self) -> None:
        self.instructions = SimpleNamespace(manual_only=True)

    def to_dict(self):
        return {
            "quote": {
                "quote_id": "base-quote-test",
                "dry": False,
                "state": "AWAITING_DEPOSIT",
                "source_chain": "base",
                "deposit_address": "0x" + "2" * 40,
            },
            "provider_quote": {"signature": "ed25519:test"},
            "validation": {"signature_verified": True},
            "instructions": {"manual_only": True, "supported": True},
        }


class FakeLiveFunding:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            destination_asset="nep141:usdc.tidepool-sandbox.testnet",
            api_key="secret-key",
        )
        self.store = SimpleNamespace(close=lambda: None)
        self.quote = SimpleNamespace(source_chain="base", quote_id="base-quote-test")
        self.live_calls = 0
        self.deposit_calls = 0

    def discover_tokens(self):
        return []

    def supported_routes(self):
        return []

    def prepare_swap(self, **kwargs):
        self.live_calls += 1
        return Prepared()

    def get_quote(self, quote_id):
        return self.quote

    def record_deposit(self, quote_id, tx_hash, *, submit=False):
        self.deposit_calls += 1
        return SimpleNamespace(deposit_submitted=True, quote_id=quote_id)

    def quote_summary(self, quote):
        return {
            "quote_id": quote.quote_id,
            "state": "DEPOSIT_DETECTED",
            "provider_status": "KNOWN_DEPOSIT_TX",
            "deposit_submitted": True,
        }


class Phase7BApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = make_app()
        self.funding = FakeLiveFunding()
        self.app.funding_service = self.funding

    def tearDown(self) -> None:
        self.app.close()

    def call(self, method, path, body=None):
        return self.app.handle(method, path, {}, body, client="phase7b-test")

    def base_body(self):
        return {
            "source_asset": "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet",
            "source_chain": "base",
            "amount": "1000000",
            "recipient": "notch-dev.testnet",
            "refund_to": "0x1111111111111111111111111111111111111111",
            "deposit_type": "ORIGIN_CHAIN",
            "slippage_bps": 100,
            "deadline_minutes": 15,
            "dry": False,
            "confirm_live_quote": True,
            "confirm_testnet": True,
        }

    def test_live_quote_requires_explicit_confirmation_and_keeps_quote_boundary(self):
        quote_body = self.base_body()
        quote_body.pop("confirm_live_quote")
        quote_body.pop("confirm_testnet")
        status, payload = self.call("POST", "/api/funding/quote", quote_body)
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "WET_QUOTES_DISABLED")
        body = self.base_body()
        body.pop("confirm_live_quote")
        status, payload = self.call("POST", "/api/funding/live-quote", body)
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "LIVE_QUOTE_NOT_CONFIRMED")
        status, payload = self.call("POST", "/api/funding/live-quote", self.base_body())
        self.assertEqual(status, 200)
        self.assertTrue(payload["meta"]["live_quote"])
        self.assertFalse(payload["meta"]["signed"])
        self.assertEqual(self.funding.live_calls, 1)

    def test_deposit_requires_user_submitted_hash_and_confirmation(self):
        body = {
            "quote_id": "base-quote-test",
            "tx_hash": "0x" + "a" * 64,
            "submit": True,
        }
        status, payload = self.call("POST", "/api/funding/deposit", body)
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "DEPOSIT_NOT_CONFIRMED")
        status, payload = self.call(
            "POST",
            "/api/funding/deposit",
            {**body, "user_confirmed": True},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["meta"]["signed"])
        self.assertEqual(self.funding.deposit_calls, 1)


if __name__ == "__main__":
    unittest.main()
