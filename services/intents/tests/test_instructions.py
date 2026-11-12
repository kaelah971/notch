"""Tests for exact NEAR deposit instructions."""

from __future__ import annotations

import unittest

from services.intents.config import IntentsConfig
from services.intents.instructions import build_deposit_instructions
from services.intents.models import QuoteResponse, Token
from services.intents.tests import fixtures
from services.intents.validation import ValidationError


def token(asset_id: str) -> Token:
    for item in fixtures.TOKENS:
        if item["assetId"] == asset_id:
            return Token.from_provider(item)
    raise AssertionError(asset_id)


class InstructionTests(unittest.TestCase):
    def setUp(self):
        self.config = IntentsConfig()
        self.usdt = token("nep141:usdt.tidepool-sandbox.testnet")
        self.usdc = token("nep141:usdc.tidepool-sandbox.testnet")

    def test_intents_deposit_uses_verifier_and_msg(self):
        response = QuoteResponse.from_provider(fixtures.quote_response(dry=False))
        instructions = build_deposit_instructions(
            response, self.usdt, self.usdc, self.config, now=fixtures.NOW
        )
        self.assertTrue(instructions.supported)
        self.assertEqual(len(instructions.steps), 1)
        step = instructions.steps[0]
        self.assertEqual(step.contract, "usdt.tidepool-sandbox.testnet")
        self.assertEqual(step.method, "ft_transfer_call")
        self.assertEqual(step.args["receiver_id"], "verifier.tidepool-sandbox.testnet")
        self.assertEqual(step.args["msg"], fixtures.DEPOSIT_ADDRESS)
        self.assertEqual(step.args["amount"], "1000000")
        self.assertEqual(step.attached_deposit_yocto, "1")
        self.assertEqual(step.gas_tgas, 100)
        self.assertNotIn("storage_deposit", step.action)

    def test_origin_chain_requires_storage_and_exact_address(self):
        response = QuoteResponse.from_provider(
            fixtures.quote_response(dry=False, deposit_type="ORIGIN_CHAIN")
        )
        instructions = build_deposit_instructions(
            response, self.usdt, self.usdc, self.config, now=fixtures.NOW
        )
        self.assertEqual(len(instructions.steps), 2)
        storage, transfer = instructions.steps
        self.assertEqual(storage.method, "storage_deposit")
        self.assertEqual(storage.args["account_id"], fixtures.DEPOSIT_ADDRESS)
        self.assertEqual(storage.attached_deposit_yocto, "1250000000000000000000")
        self.assertEqual(storage.gas_tgas, 30)
        self.assertEqual(transfer.method, "ft_transfer")
        self.assertEqual(transfer.args["receiver_id"], fixtures.DEPOSIT_ADDRESS)
        self.assertEqual(transfer.args["amount"], "1000000")
        self.assertEqual(transfer.attached_deposit_yocto, "1")
        self.assertEqual(transfer.gas_tgas, 30)

    def test_memo_is_preserved(self):
        payload = fixtures.quote_response(dry=False)
        payload["quote"]["depositMemo"] = "memo-123"
        payload["quoteRequest"]["depositMode"] = "MEMO"
        response = QuoteResponse.from_provider(payload)
        instructions = build_deposit_instructions(
            response, self.usdt, self.usdc, self.config, now=fixtures.NOW
        )
        self.assertEqual(instructions.deposit_memo, "memo-123")
        self.assertEqual(instructions.steps[0].args["memo"], "memo-123")

    def test_expired_quote_refused(self):
        payload = fixtures.quote_response(dry=False)
        payload["quote"]["deadline"] = "2026-11-12T06:59:00Z"
        response = QuoteResponse.from_provider(payload)
        with self.assertRaises(ValidationError) as ctx:
            build_deposit_instructions(
                response, self.usdt, self.usdc, self.config, now=fixtures.NOW
            )
        self.assertEqual(ctx.exception.code, "QUOTE_EXPIRED")

    def test_dry_quote_has_no_instructions(self):
        response = QuoteResponse.from_provider(fixtures.quote_response(dry=True))
        with self.assertRaises(ValidationError) as ctx:
            build_deposit_instructions(
                response, self.usdt, self.usdc, self.config, now=fixtures.NOW
            )
        self.assertEqual(ctx.exception.code, "DRY_QUOTE")

    def test_non_near_chain_is_explicitly_unsupported(self):
        source = token(
            "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet"
        )
        response = QuoteResponse.from_provider(fixtures.quote_response(dry=False))
        instructions = build_deposit_instructions(
            response, source, self.usdc, self.config, now=fixtures.NOW
        )
        self.assertFalse(instructions.supported)
        self.assertIn("not implemented", instructions.blocker)
        self.assertEqual(instructions.steps, [])


if __name__ == "__main__":
    unittest.main()
