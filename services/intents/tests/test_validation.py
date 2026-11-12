"""Validation and base-unit tests for S4 funding."""

from __future__ import annotations

import unittest

from services.intents.config import IntentsConfig
from services.intents.models import QuoteRequest, QuoteResponse, Token
from services.intents.tests import fixtures
from services.intents.validation import (
    ValidationError,
    format_base_units,
    is_near_account,
    parse_base_units,
    select_route,
    supported_routes,
    validate_quote_response,
    validate_request,
)


def tokens():
    return [Token.from_provider(item) for item in fixtures.TOKENS]


def request(**overrides):
    base = dict(
        dry=False,
        swap_type="EXACT_INPUT",
        slippage_tolerance=100,
        origin_asset="nep141:usdt.tidepool-sandbox.testnet",
        deposit_type="INTENTS",
        destination_asset="nep141:usdc.tidepool-sandbox.testnet",
        amount="1000000",
        refund_to="notch-dev.testnet",
        refund_type="INTENTS",
        recipient="notch-dev.testnet",
        recipient_type="DESTINATION_CHAIN",
        deadline=fixtures.DEADLINE,
        deposit_mode="SIMPLE",
    )
    base.update(overrides)
    return QuoteRequest(**base)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = IntentsConfig()
        self.tokens = tokens()

    def test_route_discovery(self):
        route = select_route(self.tokens, "nep141:usdt.tidepool-sandbox.testnet", self.config)
        self.assertEqual(route.source.symbol, "USDT")
        self.assertEqual(route.destination.asset_id, self.config.destination_asset)
        routes = supported_routes(self.tokens, self.config)
        symbols = {route.source.symbol for route in routes}
        self.assertIn("USDT", symbols)
        self.assertIn("wNEAR", symbols)
        self.assertNotIn("USDC", symbols)

    def test_unsupported_chain_route(self):
        with self.assertRaises(ValidationError) as ctx:
            select_route(
                self.tokens,
                "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet",
                self.config,
            )
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_SOURCE_CHAIN")

    def test_same_asset_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            select_route(
                self.tokens,
                "nep141:usdc.tidepool-sandbox.testnet",
                self.config,
            )
        self.assertEqual(ctx.exception.code, "SAME_ASSET")

    def test_wrong_destination_rejected(self):
        req = request(destination_asset="nep141:wnear.tidepool-sandbox.testnet")
        with self.assertRaises(ValidationError) as ctx:
            validate_request(req, self.tokens, self.config, now=fixtures.NOW)
        self.assertEqual(ctx.exception.code, "WRONG_DESTINATION")

    def test_amount_rules(self):
        with self.assertRaises(ValidationError) as ctx:
            parse_base_units("1.0")
        self.assertEqual(ctx.exception.code, "INVALID_AMOUNT")
        with self.assertRaises(ValidationError):
            parse_base_units("0")
        with self.assertRaises(ValidationError) as ctx:
            validate_request(
                request(amount="1"), self.tokens, self.config, now=fixtures.NOW
            )
        self.assertEqual(ctx.exception.code, "AMOUNT_BELOW_MINIMUM")
        with self.assertRaises(ValidationError) as ctx:
            validate_request(
                request(amount="11000000"), self.tokens, self.config, now=fixtures.NOW
            )
        self.assertEqual(ctx.exception.code, "AMOUNT_ABOVE_MAXIMUM")

    def test_expired_and_far_deadline(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_request(
                request(deadline="2026-11-12T06:59:00Z"),
                self.tokens,
                self.config,
                now=fixtures.NOW,
            )
        self.assertEqual(ctx.exception.code, "QUOTE_EXPIRED")
        with self.assertRaises(ValidationError) as ctx:
            validate_request(
                request(deadline="2026-11-13T07:00:00Z"),
                self.tokens,
                self.config,
                now=fixtures.NOW,
            )
        self.assertEqual(ctx.exception.code, "DEADLINE_TOO_FAR")

    def test_invalid_slippage_and_recipient(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_request(
                request(slippage_tolerance=0), self.tokens, self.config, now=fixtures.NOW
            )
        self.assertEqual(ctx.exception.code, "INVALID_SLIPPAGE")
        with self.assertRaises(ValidationError) as ctx:
            validate_request(
                request(recipient="Not-An-Account"),
                self.tokens,
                self.config,
                now=fixtures.NOW,
            )
        self.assertEqual(ctx.exception.code, "INVALID_RECIPIENT")

    def test_valid_quote_response(self):
        req = request()
        route = select_route(self.tokens, req.origin_asset, self.config)
        response = QuoteResponse.from_provider(fixtures.quote_response(dry=False))
        validation = validate_quote_response(
            response, req, route, self.config, now=fixtures.NOW
        )
        self.assertEqual(validation.expires_at.isoformat(), "2026-11-12T07:30:00+00:00")
        self.assertEqual(validation.implied_fee_usd, "0.0026")

    def test_quote_amount_mismatch(self):
        req = request()
        route = select_route(self.tokens, req.origin_asset, self.config)
        payload = fixtures.quote_response(dry=False, amount_out="900000")
        payload["quote"]["amountIn"] = "999999"
        response = QuoteResponse.from_provider(payload)
        with self.assertRaises(ValidationError) as ctx:
            validate_quote_response(response, req, route, self.config, now=fixtures.NOW)
        self.assertEqual(ctx.exception.code, "AMOUNT_IN_MISMATCH")

    def test_quote_min_out_exceeds_out(self):
        req = request()
        route = select_route(self.tokens, req.origin_asset, self.config)
        response = QuoteResponse.from_provider(
            fixtures.quote_response(dry=False, amount_out="900000", min_amount_out="900001")
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_quote_response(response, req, route, self.config, now=fixtures.NOW)
        self.assertEqual(ctx.exception.code, "INVALID_MIN_AMOUNT_OUT")

    def test_invalid_signature_shape(self):
        req = request()
        route = select_route(self.tokens, req.origin_asset, self.config)
        payload = fixtures.quote_response(dry=False)
        payload["signature"] = "not-a-signature"
        response = QuoteResponse.from_provider(payload)
        with self.assertRaises(ValidationError) as ctx:
            validate_quote_response(response, req, route, self.config, now=fixtures.NOW)
        self.assertEqual(ctx.exception.code, "INVALID_QUOTE_SIGNATURE")

    def test_dry_quote_has_no_deposit_address(self):
        req = request(dry=True)
        route = select_route(self.tokens, req.origin_asset, self.config)
        response = QuoteResponse.from_provider(fixtures.quote_response(dry=True))
        validation = validate_quote_response(
            response, req, route, self.config, now=fixtures.NOW
        )
        self.assertIsNone(response.quote.deposit_address)
        self.assertIsNotNone(validation.expires_at)

    def test_live_quote_expired(self):
        req = request()
        route = select_route(self.tokens, req.origin_asset, self.config)
        payload = fixtures.quote_response(dry=False)
        payload["quote"]["deadline"] = "2026-11-12T06:59:00Z"
        response = QuoteResponse.from_provider(payload)
        with self.assertRaises(ValidationError) as ctx:
            validate_quote_response(response, req, route, self.config, now=fixtures.NOW)
        self.assertEqual(ctx.exception.code, "QUOTE_EXPIRED")

    def test_base_unit_formatting(self):
        self.assertEqual(format_base_units("1000000", 6), "1")
        self.assertEqual(format_base_units("996968", 6), "0.996968")
        self.assertEqual(format_base_units("100000000000000000000000", 24), "0.1")

    def test_near_accounts(self):
        self.assertTrue(is_near_account("notch-dev.testnet"))
        self.assertTrue(is_near_account("f" * 64))
        self.assertFalse(is_near_account("Notch-Dev.testnet"))
        self.assertFalse(is_near_account("x"))


if __name__ == "__main__":
    unittest.main()
