"""Phase 7C API boundary tests for official Mainnet dry-only discovery and quotes."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.web_api.tests.test_api import make_app


class FakeOfficialFunding:
    auth_mode = "unauthenticated_public_api"

    def __init__(self):
        self.store = SimpleNamespace(close=lambda: None)

    def discovery(self):
        return {
            "provider": "Official NEAR Intents 1Click API",
            "provider_id": "near-intents-1click-mainnet",
            "network": "Mainnet",
            "environment": "NOTCH_MAINNET_FUTURE",
            "tokens": [{"asset_id": "nep141:base-usdc.omft.near", "symbol": "USDC"}],
            "source_tokens": [{"asset_id": "nep141:base-usdc.omft.near", "symbol": "USDC", "blockchain": "base"}],
            "destination_candidates": [{"asset_id": "nep141:near-usdc.omft.near", "symbol": "USDC", "blockchain": "near"}],
            "routes": [],
            "source_chains": ["base"],
            "destination_asset": "nep141:near-usdc.omft.near",
            "recipient": "notch.near",
            "quote_enabled": True,
            "quote_mode": "dry_only",
            "auth_mode": self.auth_mode,
            "auth_configured": False,
            "credentials_exposed": False,
            "fee_notice": "Unauthenticated public quotes include the documented 25 bps fee.",
            "execution_supported": False,
            "execution_reasons": ["Notch execution is disabled."],
            "unavailable_reasons": ["No partner JWT configured."],
            "signature_public_key_id": "official-oneclick-manager-ed25519",
            "observed_at": "2026-11-14T07:00:00Z",
        }

    def dry_quote(self, **kwargs):
        return SimpleNamespace(
            to_dict=lambda: {
                "quote": {
                    "quote_id": "official-api-test",
                    "dry": True,
                    "source_asset": kwargs["source_asset"],
                    "destination_asset": kwargs["destination_asset"],
                    "amount_in": kwargs["amount"],
                    "amount_out": "995000",
                    "min_amount_out": "985050",
                    "deposit_address": None,
                },
                "provider_quote": {"quote": {"amount_in": kwargs["amount"], "amount_out": "995000"}},
                "validation": {"signature_verified": True},
                "instructions": {"supported": False, "manual_only": True},
            }
        )


class Phase7CApiTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.app.official_funding_service = FakeOfficialFunding()

    def tearDown(self):
        self.app.close()

    def call(self, method, path, body=None):
        return self.app.handle(method, path, {}, body, client="phase7c-test")

    def test_mainnet_discovery_is_separate_from_tidepool_testnet(self):
        status, payload = self.call("GET", "/api/funding/mainnet/tokens")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["network"], "Mainnet")
        self.assertFalse(payload["meta"]["execution_supported"])
        self.assertFalse(payload["meta"]["credentials_exposed"])

    def test_mainnet_quote_requires_dry_true(self):
        body = {
            "source_asset": "nep141:base-usdc.omft.near",
            "destination_asset": "nep141:near-usdc.omft.near",
            "source_chain": "base",
            "amount": "1000000",
            "recipient": "notch.near",
            "refund_to": "0x1111111111111111111111111111111111111111",
            "dry": False,
        }
        status, payload = self.call("POST", "/api/funding/mainnet/quote", body)
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "OFFICIAL_MAINNET_DRY_ONLY")

    def test_mainnet_quote_cannot_receive_execution_fields_and_preserves_read_only_meta(self):
        body = {
            "source_asset": "nep141:base-usdc.omft.near",
            "destination_asset": "nep141:near-usdc.omft.near",
            "source_chain": "base",
            "amount": "1000000",
            "recipient": "notch.near",
            "refund_to": "0x1111111111111111111111111111111111111111",
            "dry": True,
        }
        status, payload = self.call("POST", "/api/funding/mainnet/quote", body)
        self.assertEqual(status, 200)
        self.assertTrue(payload["meta"]["dry"])
        self.assertFalse(payload["meta"]["signed"])
        self.assertFalse(payload["meta"]["broadcast"])
        self.assertFalse(payload["meta"]["execution_supported"])
        self.assertIsNone(payload["data"]["quote"]["deposit_address"])
        status, payload = self.call("POST", "/api/funding/mainnet/quote", {**body, "confirm_live_quote": True})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_BODY")
        status, payload = self.call("POST", "/api/funding/mainnet/quote", {**body, "dry": True, "deposit_type": "INTENTS"})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_DEPOSIT_TYPE")

    def test_unconfigured_official_provider_is_explicit(self):
        self.app.official_funding_service = None
        status, payload = self.call("GET", "/api/funding/mainnet/tokens")
        self.assertEqual(status, 200)
        self.assertFalse(payload["data"]["quote_enabled"])
        self.assertTrue(payload["data"]["unavailable_reasons"])


if __name__ == "__main__":
    unittest.main()
