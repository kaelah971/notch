"""Phase 7C official NEAR Intents Mainnet read-only integration tests."""

from __future__ import annotations

import unittest

from services.intents.models import QuoteResponse, Token
from services.intents.official import (
    OFFICIAL_ONE_CLICK_MANAGER_PUBLIC_KEY,
    OfficialMainnetConfig,
    OfficialMainnetFundingService,
    OfficialOneClickClient,
)
from services.intents.signature import verify_quote_signature
from services.intents.validation import ValidationError

BASE_MAINNET = "nep141:base-0x833589fcd6edb6e08f4c7c32d4f71b54bda02913.omft.near"
NEAR_USDC_MAINNET = "nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1"
BASE_TESTNET = "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet"
REFUND = "0x1111111111111111111111111111111111111111"

MAINNET_TOKENS = [
    {
        "assetId": BASE_MAINNET,
        "decimals": 6,
        "blockchain": "base",
        "symbol": "USDC",
        "price": 0.9996,
        "contractAddress": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    },
    {
        "assetId": NEAR_USDC_MAINNET,
        "decimals": 6,
        "blockchain": "near",
        "symbol": "USDC",
        "price": 0.9996,
        "contractAddress": "17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1",
    },
]

OFFICIAL_RAW = {
    "quote": {
        "amountIn": "1000000",
        "amountInFormatted": "1.0",
        "amountInUsd": "0.999604000000",
        "minAmountIn": "1000000",
        "amountOut": "995596",
        "amountOutFormatted": "0.995596",
        "amountOutUsd": "0.995201743984",
        "minAmountOut": "985640",
        "timeEstimate": 35,
        "refundFee": "2400",
        "withdrawFee": "4202",
    },
    "quoteRequest": {
        "dry": True,
        "depositMode": "SIMPLE",
        "swapType": "EXACT_INPUT",
        "slippageTolerance": 100,
        "originAsset": BASE_MAINNET,
        "depositType": "ORIGIN_CHAIN",
        "destinationAsset": NEAR_USDC_MAINNET,
        "amount": "1000000",
        "refundTo": REFUND,
        "refundType": "ORIGIN_CHAIN",
        "recipient": "notch.near",
        "recipientType": "DESTINATION_CHAIN",
        "deadline": "2026-11-14T07:10:48.201Z",
    },
    "signature": "ed25519:6kRyxBHB78hTbX4EcDywgYo99M1AWuthTJjx95TU7SZoMmkMkhvE2mvLNVaYMrfyhkM6E6nYUFFMNztasXtqdGV",
    "timestamp": "2026-11-14T06:55:48.626Z",
    "correlationId": "80a1c8fb-3969-462d-9fcf-79e0c75fba47",
}


class FakeOfficialClient:
    def __init__(self) -> None:
        self.tokens = [Token.from_provider(item) for item in MAINNET_TOKENS]
        self.requests = []

    def get_tokens(self):
        return list(self.tokens)

    def quote(self, request):
        self.requests.append(request)
        payload = {
            "quote": {
                "amountIn": request.amount,
                "amountInFormatted": "1.0",
                "amountInUsd": "0.9996",
                "minAmountIn": request.amount,
                "amountOut": "995000",
                "amountOutFormatted": "0.995",
                "amountOutUsd": "0.9946",
                "minAmountOut": "985050",
                "timeEstimate": 35,
                "refundFee": "2400",
                "withdrawFee": "4202",
            },
            "quoteRequest": request.to_provider_dict(),
            "signature": "ed25519:" + "1" * 88,
            "timestamp": "2026-11-12T07:00:00Z",
            "correlationId": "official-test-quote",
        }
        return QuoteResponse.from_provider(payload)


class Phase7COfficialTests(unittest.TestCase):
    def config(self, **overrides):
        values = {
            "destination_asset": NEAR_USDC_MAINNET,
            "recipient": "notch.near",
            "refund_to": REFUND,
            "verify_quote_signatures": False,
        }
        values.update(overrides)
        return OfficialMainnetConfig(**values)

    def test_official_signature_uses_official_manager_key_not_tidepool_key(self):
        response = QuoteResponse.from_provider(OFFICIAL_RAW)
        self.assertTrue(verify_quote_signature(response, OFFICIAL_ONE_CLICK_MANAGER_PUBLIC_KEY))
        self.assertFalse(verify_quote_signature(response))

    def test_discovery_preserves_mainnet_identity_and_never_maps_testnet_assets(self):
        service = OfficialMainnetFundingService(config=self.config(), client=FakeOfficialClient())
        discovery = service.discovery()
        self.assertEqual(discovery["network"], "Mainnet")
        self.assertEqual(discovery["environment"], "NOTCH_MAINNET_FUTURE")
        self.assertEqual(discovery["destination_asset"], NEAR_USDC_MAINNET)
        self.assertEqual(discovery["source_tokens"][0]["asset_id"], BASE_MAINNET)
        self.assertNotIn(".testnet", discovery["destination_asset"])
        self.assertFalse(discovery["execution_supported"])

    def test_dry_quote_is_genuine_shape_but_has_no_deposit_address(self):
        client = FakeOfficialClient()
        service = OfficialMainnetFundingService(config=self.config(), client=client)
        result = service.dry_quote(
            source_asset=BASE_MAINNET,
            source_chain="base",
            amount="1000000",
            recipient="notch.near",
            refund_to=REFUND,
            destination_asset=NEAR_USDC_MAINNET,
        )
        self.assertTrue(result.quote.dry)
        self.assertIsNone(result.quote.deposit_address)
        self.assertEqual(result.quote.source_decimals, 6)
        self.assertEqual(result.quote.destination_decimals, 6)
        self.assertEqual(client.requests[0].dry, True)

    def test_wet_mainnet_and_testnet_routes_fail_closed(self):
        service = OfficialMainnetFundingService(config=self.config(), client=FakeOfficialClient())
        with self.assertRaisesRegex(ValidationError, "read-only"):
            service.prepare_swap(source_asset=BASE_MAINNET)
        with self.assertRaisesRegex(ValidationError, "not in the live"):
            service.dry_quote(
                source_asset=BASE_TESTNET,
                source_chain="base",
                amount="1000000",
                recipient="notch.near",
                refund_to=REFUND,
                destination_asset=NEAR_USDC_MAINNET,
            )

    def test_missing_partner_key_is_explicit_without_exposing_credentials(self):
        service = OfficialMainnetFundingService(config=self.config(api_key=None), client=FakeOfficialClient())
        discovery = service.discovery()
        self.assertEqual(discovery["auth_mode"], "unauthenticated_public_api")
        self.assertFalse(discovery["auth_configured"])
        self.assertFalse(discovery["credentials_exposed"])
        self.assertIn("25 bps", discovery["fee_notice"])
        self.assertTrue(discovery["unavailable_reasons"])

    def test_invalid_official_base_url_fails_closed(self):
        with self.assertRaises(ValueError):
            OfficialMainnetConfig(base_url="https://www.usetidepool.tech")

    def test_official_client_uses_server_side_bearer_auth_only(self):
        client = OfficialOneClickClient(self.config(api_key="partner-jwt"))
        headers = client._headers()
        self.assertEqual(headers["Authorization"], "Bearer partner-jwt")
        self.assertNotIn("X-API-Key", headers)

    def test_official_client_does_not_offer_status_or_deposit_submission(self):
        client = OfficialOneClickClient(self.config())
        with self.assertRaisesRegex(ValidationError, "read-only"):
            client.submit_deposit(tx_hash="0x" + "a" * 64, deposit_address="0x" + "b" * 40)
        with self.assertRaisesRegex(ValidationError, "disabled"):
            client.get_status(deposit_address="0x" + "b" * 40)


if __name__ == "__main__":
    unittest.main()
