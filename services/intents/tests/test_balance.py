"""Balance readiness and destination-increase verification tests."""

from __future__ import annotations

import base64
import json
import unittest

from services.intents.balance import (
    NearRpcClient,
    NearRpcError,
    read_funding_readiness,
    verify_destination_balance,
)
from services.intents.models import FundingQuote, FundingState, Token
from services.intents.tests import fixtures


def token(asset_id: str) -> Token:
    return next(Token.from_provider(item) for item in fixtures.TOKENS if item["assetId"] == asset_id)


class FakeReader:
    def __init__(self, balance: int, storage=None):
        self.balance = balance
        self.storage = storage

    def ft_balance_of(self, contract, account):
        return self.balance

    def storage_balance_of(self, contract, account):
        return self.storage


def quote(balance_before="100000000") -> FundingQuote:
    return FundingQuote(
        quote_id="q1",
        correlation_id="q1",
        state=FundingState.PROCESSING,
        dry=False,
        source_asset="nep141:usdt.tidepool-sandbox.testnet",
        source_symbol="USDT",
        source_chain="near",
        source_decimals=6,
        destination_asset="nep141:usdc.tidepool-sandbox.testnet",
        destination_symbol="USDC",
        destination_decimals=6,
        amount_in="1000000",
        amount_out="996968",
        min_amount_out="986998",
        slippage_bps=100,
        recipient="notch-dev.testnet",
        refund_to="notch-dev.testnet",
        deposit_type="INTENTS",
        refund_type="INTENTS",
        deadline=fixtures.DEADLINE,
        deposit_address=fixtures.DEPOSIT_ADDRESS,
        deposit_memo=None,
        signature=fixtures.SIGNATURE,
        quote_timestamp="2026-11-12T07:00:01Z",
        created_at="2026-11-12T07:00:02Z",
        updated_at="2026-11-12T07:00:02Z",
        balance_before=balance_before,
    )


class BalanceTests(unittest.TestCase):
    def test_readiness_registered_and_above_minimum(self):
        reader = FakeReader(100_000_000, {"total": "1", "available": "0"})
        readiness = read_funding_readiness(
            reader,
            account="notch-dev.testnet",
            token=token("nep141:usdc.tidepool-sandbox.testnet"),
            min_market_entry=1_000_000,
            now=fixtures.NOW,
        )
        self.assertTrue(readiness.ready)
        self.assertEqual(readiness.balance, "100000000")

    def test_readiness_missing_storage(self):
        reader = FakeReader(100_000_000, None)
        readiness = read_funding_readiness(
            reader,
            account="notch-dev.testnet",
            token=token("nep141:usdc.tidepool-sandbox.testnet"),
            min_market_entry=1_000_000,
            now=fixtures.NOW,
        )
        self.assertFalse(readiness.ready)
        self.assertIn("storage", readiness.blocker)

    def test_readiness_below_minimum(self):
        reader = FakeReader(500_000, {"total": "1"})
        readiness = read_funding_readiness(
            reader,
            account="notch-dev.testnet",
            token=token("nep141:usdc.tidepool-sandbox.testnet"),
            min_market_entry=1_000_000,
            now=fixtures.NOW,
        )
        self.assertFalse(readiness.ready)
        self.assertIn("below", readiness.blocker)

    def test_verified_destination_increase(self):
        reader = FakeReader(100_996_968)
        check = verify_destination_balance(
            reader,
            quote(),
            token("nep141:usdc.tidepool-sandbox.testnet"),
            now=fixtures.NOW,
        )
        self.assertTrue(check.verified)
        self.assertEqual(check.delta, "996968")

    def test_no_increase_is_not_verified(self):
        reader = FakeReader(100_000_000)
        check = verify_destination_balance(
            reader,
            quote(),
            token("nep141:usdc.tidepool-sandbox.testnet"),
            now=fixtures.NOW,
        )
        self.assertFalse(check.verified)
        self.assertIn("below required", check.error)

    def test_missing_before_balance_is_not_verified(self):
        reader = FakeReader(100_996_968)
        check = verify_destination_balance(
            reader,
            quote(balance_before=None),
            token("nep141:usdc.tidepool-sandbox.testnet"),
            now=fixtures.NOW,
        )
        self.assertFalse(check.verified)
        self.assertIn("not recorded", check.error)

    def test_rpc_client_parses_ft_balance(self):
        encoded = base64.b64encode(b'"100000000"').decode("ascii")

        def transport(payload, timeout):
            return {"result": list(base64.b64decode(encoded))}

        reader = NearRpcClient(rpc_url="https://rpc.invalid", transport=transport)
        self.assertEqual(
            reader.ft_balance_of("usdc.tidepool-sandbox.testnet", "notch-dev.testnet"),
            100_000_000,
        )

    def test_rpc_client_requires_finalized_block_provenance(self):
        encoded = base64.b64encode(b'"100000000"').decode("ascii")

        def transport(payload, timeout):
            return {"result": list(base64.b64decode(encoded))}

        reader = NearRpcClient(rpc_url="https://rpc.invalid", transport=transport)
        with self.assertRaises(NearRpcError):
            reader.ft_balance_finalized(
                "usdc.tidepool-sandbox.testnet",
                "notch-dev.testnet",
            )


if __name__ == "__main__":
    unittest.main()
