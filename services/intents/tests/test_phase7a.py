"""Phase 7A cross-chain funding discovery and dry-quote safeguards."""

from __future__ import annotations

import unittest

from services.intents.config import IntentsConfig
from services.intents.models import QuoteRequest, Token
from services.intents.tests import fixtures
from services.intents.validation import ValidationError, is_valid_refund_address, select_route, validate_request


class Phase7AFundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = IntentsConfig()
        self.tokens = [Token.from_provider(item) for item in fixtures.TOKENS]

    def external_request(self, **overrides: object) -> QuoteRequest:
        values = fixtures.quote_request(dry=True)
        values.update(
            {
                "originAsset": "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet",
                "depositType": "ORIGIN_CHAIN",
                "refundTo": "0x1111111111111111111111111111111111111111",
                "refundType": "ORIGIN_CHAIN",
            }
        )
        values.update(overrides)
        return QuoteRequest(
            dry=values["dry"],
            swap_type=values["swapType"],
            slippage_tolerance=values["slippageTolerance"],
            origin_asset=values["originAsset"],
            deposit_type=values["depositType"],
            destination_asset=values["destinationAsset"],
            amount=values["amount"],
            refund_to=values["refundTo"],
            refund_type=values["refundType"],
            recipient=values["recipient"],
            recipient_type=values["recipientType"],
            deadline=values["deadline"],
            deposit_mode=values["depositMode"],
        )

    def test_external_discovery_preserves_asset_ids_and_decimals(self) -> None:
        route = select_route(
            self.tokens,
            "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet",
            self.config,
            source_chain="external",
        )
        self.assertEqual(route.source.blockchain, "base")
        self.assertEqual(route.source.decimals, 6)
        self.assertEqual(route.destination.asset_id, "nep141:usdc.tidepool-sandbox.testnet")
        self.assertEqual(route.destination.decimals, 6)

    def test_external_request_requires_chain_specific_refund_address(self) -> None:
        request = self.external_request()
        route = validate_request(
            request,
            self.tokens,
            self.config,
            now=fixtures.NOW,
            source_chain="external",
        )
        self.assertEqual(route.source.blockchain, "base")
        self.assertTrue(is_valid_refund_address(request.refund_to, "base"))
        self.assertFalse(is_valid_refund_address("not-an-address", "base"))

    def test_missing_or_wrong_refund_address_is_rejected(self) -> None:
        for refund_to in ("", "notch-dev.testnet"):
            with self.subTest(refund_to=refund_to):
                with self.assertRaisesRegex(ValidationError, "valid base testnet address"):
                    validate_request(
                        self.external_request(refundTo=refund_to),
                        self.tokens,
                        self.config,
                        now=fixtures.NOW,
                        source_chain="external",
                    )

    def test_external_route_rejects_near_source_and_mainnet_destination(self) -> None:
        with self.assertRaisesRegex(ValidationError, "external testnet source"):
            select_route(
                self.tokens,
                "nep141:usdt.tidepool-sandbox.testnet",
                self.config,
                source_chain="external",
            )
        with self.assertRaises(ValueError):
            IntentsConfig(destination_asset="nep141:usdc.1click.mainnet")


if __name__ == "__main__":
    unittest.main()
