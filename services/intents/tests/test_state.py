"""State-machine and idempotency tests for the funding service."""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from services.intents.balance import NearRpcClient
from services.intents.config import IntentsConfig
from services.intents.models import FundingState, QuoteResponse, StatusResponse, Token
from services.intents.service import IntentsFundingService
from services.intents.store import DuplicateDepositError, FundingStore
from services.intents.tests import fixtures
from services.intents.validation import ValidationError


class FakeClient:
    def __init__(self):
        self.tokens = [Token.from_provider(item) for item in fixtures.TOKENS]
        self.statuses: list[StatusResponse] = []
        self.submit_status: StatusResponse | None = None
        self.quote_calls = 0
        self.status_calls = 0
        self.submit_calls = 0
        self.correlation_id: str | None = None

    def get_tokens(self, *, include_ondo=False):
        return list(self.tokens)

    def quote(self, request):
        self.quote_calls += 1
        payload = fixtures.quote_response(
            dry=request.dry,
            deposit_type=request.deposit_type,
            amount=request.amount,
        )
        if self.correlation_id:
            payload["correlationId"] = self.correlation_id
        else:
            payload["correlationId"] = f"quote-test-{self.quote_calls}"
        return QuoteResponse.from_provider(payload)

    def get_status(self, *, deposit_address, memo=None):
        self.status_calls += 1
        if not self.statuses:
            raise AssertionError("no fake status queued")
        return self.statuses.pop(0)

    def submit_deposit(self, *, tx_hash, deposit_address, near_sender_account=None, memo=None):
        self.submit_calls += 1
        if self.submit_status is None:
            raise AssertionError("no submit status queued")
        return self.submit_status


class FakeReader:
    def __init__(self, balance=100_000_000):
        self.balance = balance
        self.calls = 0

    def ft_balance_of(self, contract, account):
        self.calls += 1
        return self.balance

    def storage_balance_of(self, contract, account):
        return {"total": "1250000000000000000000", "available": "0"}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FundingStore(Path(self.tmp.name) / "funding.sqlite3")
        self.config = IntentsConfig(data_dir=self.tmp.name)
        self.client = FakeClient()
        self.reader = FakeReader()
        self.now = fixtures.NOW
        self.service = IntentsFundingService(
            client=self.client,
            store=self.store,
            config=self.config,
            reader=self.reader,
            now_fn=lambda: self.now,
            sleep=lambda _: None,
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def prepare(self):
        return self.service.prepare_swap(
            source_asset="nep141:usdt.tidepool-sandbox.testnet",
            amount="1000000",
            recipient="notch-dev.testnet",
            deposit_type="INTENTS",
        )

    def test_prepare_is_awaiting_deposit_and_records_before_balance(self):
        prepared = self.prepare()
        self.assertEqual(prepared.quote.state, FundingState.AWAITING_DEPOSIT)
        self.assertEqual(prepared.quote.balance_before, "100000000")
        self.assertEqual(prepared.quote.deposit_address, fixtures.DEPOSIT_ADDRESS)
        self.assertEqual(prepared.instructions.steps[0].args["msg"], fixtures.DEPOSIT_ADDRESS)
        self.assertEqual(len(self.store.list_events(prepared.quote.quote_id)), 1)

    def test_record_deposit_is_idempotent_and_rejects_second_tx(self):
        prepared = self.prepare()
        first = self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.assertEqual(first.deposit_tx_hash, "tx-a")
        again = self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.assertEqual(again.deposit_tx_hash, "tx-a")
        with self.assertRaises(DuplicateDepositError):
            self.service.record_deposit(prepared.quote.quote_id, "tx-b")

    def test_status_flow_success_requires_balance_increase(self):
        prepared = self.prepare()
        self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.client.statuses = [
            StatusResponse.from_provider(fixtures.status_payload("PENDING_DEPOSIT")),
            StatusResponse.from_provider(fixtures.status_payload("PROCESSING")),
            StatusResponse.from_provider(fixtures.status_payload("SUCCESS")),
        ]
        self.reader.balance = 100_000_000
        quote = self.service.refresh_status(prepared.quote.quote_id, max_attempts=3)
        self.assertEqual(quote.state, FundingState.PROCESSING)
        self.assertFalse(quote.balance_verified)
        self.assertEqual(quote.provider_status, "SUCCESS")

        self.reader.balance = 100_996_968
        quote = self.service.verify_balance(prepared.quote.quote_id)
        self.assertTrue(quote.balance_verified)
        self.assertEqual(quote.balance_delta, "996968")
        self.assertEqual(quote.state, FundingState.SUCCESS)

    def test_success_with_verified_balance_in_same_poll(self):
        prepared = self.prepare()
        self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.reader.balance = 100_996_968
        self.client.statuses = [
            StatusResponse.from_provider(fixtures.status_payload("SUCCESS")),
        ]
        quote = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertEqual(quote.state, FundingState.SUCCESS)
        self.assertTrue(quote.balance_verified)

    def test_refunded_and_failed_are_terminal(self):
        prepared = self.prepare()
        self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.client.statuses = [
            StatusResponse.from_provider(
                fixtures.status_payload(
                    "REFUNDED",
                    refunded_amount="1000000",
                    refund_reason="PARTIAL_DEPOSIT",
                    near_tx_hashes=["refund-tx"],
                )
            )
        ]
        quote = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertEqual(quote.state, FundingState.REFUNDED)
        self.assertEqual(quote.refunded_amount, "1000000")
        self.assertEqual(quote.refund_reason, "PARTIAL_DEPOSIT")
        self.assertEqual(quote.refund_tx_hash, "refund-tx")

        prepared2 = self.prepare()
        self.service.record_deposit(prepared2.quote.quote_id, "tx-b")
        self.client.statuses = [
            StatusResponse.from_provider(
                fixtures.status_payload("FAILED", refund_reason="SWAP_FAILED")
            )
        ]
        quote2 = self.service.refresh_status(prepared2.quote.quote_id, max_attempts=1)
        self.assertEqual(quote2.state, FundingState.FAILED)
        self.assertEqual(quote2.last_error, "SWAP_FAILED")

    def test_expired_quote_cannot_be_funded(self):
        prepared = self.prepare()
        self.now = fixtures.NOW + timedelta(minutes=31)
        with self.assertRaises(ValidationError) as ctx:
            self.service.record_deposit(prepared.quote.quote_id, "tx-late")
        self.assertEqual(ctx.exception.code, "QUOTE_EXPIRED")
        self.assertEqual(self.store.require_quote(prepared.quote.quote_id).state, FundingState.EXPIRED)

    def test_pending_after_deadline_marks_expired(self):
        prepared = self.prepare()
        self.now = fixtures.NOW + timedelta(minutes=31)
        self.client.statuses = [
            StatusResponse.from_provider(fixtures.status_payload("PENDING_DEPOSIT"))
        ]
        quote = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertEqual(quote.state, FundingState.EXPIRED)

    def test_dry_quote_has_no_deposit_or_status(self):
        prepared = self.service.dry_quote(
            source_asset="nep141:usdt.tidepool-sandbox.testnet",
            amount="1000000",
            recipient="notch-dev.testnet",
        )
        self.assertEqual(prepared.quote.state, FundingState.QUOTED)
        self.assertIsNone(prepared.instructions)
        with self.assertRaises(ValidationError):
            self.service.deposit_instructions(prepared.quote.quote_id)
        with self.assertRaises(ValidationError):
            self.service.refresh_status(prepared.quote.quote_id)

    def test_submit_deposit_updates_provider_status(self):
        prepared = self.prepare()
        self.client.submit_status = StatusResponse.from_provider(
            fixtures.status_payload("KNOWN_DEPOSIT_TX")
        )
        quote = self.service.record_deposit(prepared.quote.quote_id, "tx-a", submit=True)
        self.assertTrue(quote.deposit_submitted)
        self.assertEqual(quote.provider_status, "KNOWN_DEPOSIT_TX")
        self.assertEqual(quote.state, FundingState.DEPOSIT_DETECTED)
        self.assertEqual(self.client.submit_calls, 1)

    def test_quote_preparation_is_idempotent_by_correlation_id(self):
        self.client.correlation_id = "quote-test-1"
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first.quote.quote_id, second.quote.quote_id)
        self.assertEqual(self.client.quote_calls, 2)
        self.assertEqual(len(self.store.list_quotes()), 1)


if __name__ == "__main__":
    unittest.main()
