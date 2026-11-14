"""State-machine and idempotency tests for the funding service."""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from services.intents.balance import NearRpcClient, NearRpcError
from services.intents.config import IntentsConfig
from services.intents.models import (
    BalanceObservation,
    FinalizedBalanceRead,
    FundingState,
    QuoteResponse,
    StatusResponse,
    Token,
)
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
        self.finalized_calls = 0
        self.fail_balance = False
        self.bad_finalized_provenance = False
        self.rpc_url = "https://finalized.testnet.rpc"

    def ft_balance_of(self, contract, account):
        self.calls += 1
        if self.fail_balance:
            raise NearRpcError("test RPC unavailable")
        return self.balance

    def ft_balance_finalized(self, contract, account):
        self.finalized_calls += 1
        return FinalizedBalanceRead(
            balance=self.balance,
            block_height=0 if self.bad_finalized_provenance else 277_000_000 + self.finalized_calls,
            block_hash="" if self.bad_finalized_provenance else f"block-{self.finalized_calls}",
            finality="optimistic" if self.bad_finalized_provenance else "final",
            rpc_source=self.rpc_url,
        )

    def storage_balance_of(self, contract, account):
        return {"total": "1250000000000000000000", "available": "0"}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FundingStore(Path(self.tmp.name) / "funding.sqlite3")
        self.config = IntentsConfig(data_dir=self.tmp.name, verify_quote_signatures=False)
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

    def test_missing_baseline_without_observation_stays_unverified(self):
        self.reader.fail_balance = True
        prepared = self.prepare()
        self.assertIsNone(prepared.quote.balance_before)
        result = self.service.verify_balance(prepared.quote.quote_id)
        self.assertFalse(result.balance_verified)
        self.assertIn("not recorded", result.last_error or "")

    def test_matching_finalized_observation_verifies_without_mutating_quote_baseline(self):
        self.reader.fail_balance = True
        prepared = self.prepare()
        observation = self.service.capture_pre_transfer_balance(prepared.quote.quote_id)
        self.assertEqual(observation.balance, "100000000")
        self.assertIsNone(self.store.require_quote(prepared.quote.quote_id).balance_before)
        self.assertEqual(self.service.capture_pre_transfer_balance(prepared.quote.quote_id), observation)
        self.assertEqual(self.reader.finalized_calls, 1)

        self.now = fixtures.NOW + timedelta(seconds=1)
        self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.reader.balance = 100_996_968
        self.client.statuses = [StatusResponse.from_provider(fixtures.status_payload("SUCCESS"))]
        result = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertTrue(result.balance_verified)
        self.assertEqual(result.state, FundingState.SUCCESS)
        self.assertEqual(result.balance_delta, "996968")
        self.assertIsNone(result.balance_before)
        events = self.store.list_events(prepared.quote.quote_id)
        verification = next(item for item in events if item["event"] == "balance_verification")
        self.assertEqual(
            verification["data"]["baseline_observation_id"],
            observation.observation_id,
        )
        self.assertEqual(verification["data"]["after_block_height"], 277_000_002)

        self.assertEqual(self.service.refresh_status(prepared.quote.quote_id, max_attempts=1), result)
        self.assertEqual(self.client.status_calls, 1)

    def test_observation_recovery_is_idempotent(self):
        self.reader.fail_balance = True
        prepared = self.prepare()
        observation = self.service.capture_pre_transfer_balance(prepared.quote.quote_id)
        self.now = fixtures.NOW + timedelta(seconds=1)
        self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.reader.fail_balance = False
        self.reader.balance = 100_000_000
        self.client.statuses = [StatusResponse.from_provider(fixtures.status_payload("SUCCESS"))]
        pending = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertEqual(pending.state, FundingState.PROCESSING)
        self.assertFalse(pending.balance_verified)

        self.reader.balance = 100_996_968
        recovered = self.service.verify_balance(prepared.quote.quote_id)
        self.assertEqual(recovered.state, FundingState.SUCCESS)
        self.assertTrue(recovered.balance_verified)
        self.assertEqual(recovered.balance_before, None)
        finalized_calls = self.reader.finalized_calls
        again = self.service.verify_balance(prepared.quote.quote_id)
        self.assertEqual(again, recovered)
        self.assertEqual(self.reader.finalized_calls, finalized_calls)
        verification_events = [
            event for event in self.store.list_events(prepared.quote.quote_id)
            if event["event"] == "balance_verification"
        ]
        self.assertEqual(len(verification_events), 2)
        self.assertEqual(
            verification_events[-1]["data"]["baseline_observation_id"],
            observation.observation_id,
        )

    def test_mismatched_and_late_observations_are_rejected(self):
        self.reader.fail_balance = True
        prepared = self.prepare()
        wrong = BalanceObservation(
            observation_id=f"{prepared.quote.quote_id}:pre-transfer",
            quote_id=prepared.quote.quote_id,
            recipient="other.testnet",
            destination_asset=prepared.quote.destination_asset,
            token_contract="usdc.tidepool-sandbox.testnet",
            balance="100000000",
            block_height=277_000_001,
            block_hash="block-wrong",
            finality="final",
            observed_at="2026-11-12T06:59:00Z",
            rpc_source="https://finalized.testnet.rpc",
            created_at="2026-11-12T06:59:00Z",
        )
        self.store.save_balance_observation(wrong)
        self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.reader.balance = 100_996_968
        self.client.statuses = [StatusResponse.from_provider(fixtures.status_payload("SUCCESS"))]
        result = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertFalse(result.balance_verified)
        self.assertEqual(result.state, FundingState.PROCESSING)
        self.assertIn("recipient", result.last_error or "")

        prepared2 = self.prepare()
        self.service.record_deposit(prepared2.quote.quote_id, "tx-b")
        self.now = fixtures.NOW + timedelta(seconds=2)
        late = BalanceObservation(
            observation_id=f"{prepared2.quote.quote_id}:pre-transfer",
            quote_id=prepared2.quote.quote_id,
            recipient=prepared2.quote.recipient,
            destination_asset=prepared2.quote.destination_asset,
            token_contract="usdc.tidepool-sandbox.testnet",
            balance="100000000",
            block_height=277_000_003,
            block_hash="block-late",
            finality="final",
            observed_at="2026-11-12T07:00:01Z",
            rpc_source="https://finalized.testnet.rpc",
            created_at="2026-11-12T07:00:01Z",
        )
        self.store.save_balance_observation(late)
        self.reader.balance = 100_996_968
        self.client.statuses = [
            StatusResponse.from_provider(
                fixtures.status_payload("SUCCESS", correlation_id=prepared2.quote.quote_id)
            )
        ]
        result2 = self.service.refresh_status(prepared2.quote.quote_id, max_attempts=1)
        self.assertFalse(result2.balance_verified)
        self.assertIn("after deposit", result2.last_error or "")

    def test_existing_quote_baseline_verification_is_unchanged(self):
        prepared = self.prepare()
        self.assertEqual(prepared.quote.balance_before, "100000000")
        observation = self.service.capture_pre_transfer_balance(prepared.quote.quote_id)
        self.assertEqual(observation.balance, "100000000")
        self.assertEqual(self.store.require_quote(prepared.quote.quote_id).balance_before, "100000000")
        self.reader.balance = 100_996_968
        self.service.record_deposit(prepared.quote.quote_id, "tx-a")
        self.client.statuses = [StatusResponse.from_provider(fixtures.status_payload("SUCCESS"))]
        result = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertTrue(result.balance_verified)
        self.assertEqual(result.balance_before, "100000000")

    def test_untrusted_finalized_provenance_fails_closed(self):
        self.reader.fail_balance = True
        self.reader.bad_finalized_provenance = True
        prepared = self.prepare()
        with self.assertRaises(NearRpcError):
            self.service.capture_pre_transfer_balance(prepared.quote.quote_id)
        self.assertIsNone(self.store.get_balance_observation(prepared.quote.quote_id))

    def test_expired_quote_cannot_capture_pre_transfer_observation(self):
        prepared = self.prepare()
        self.now = fixtures.NOW + timedelta(minutes=31)
        with self.assertRaises(ValidationError) as ctx:
            self.service.capture_pre_transfer_balance(prepared.quote.quote_id)
        self.assertEqual(ctx.exception.code, "QUOTE_EXPIRED")
        self.assertEqual(self.store.require_quote(prepared.quote.quote_id).state, FundingState.EXPIRED)

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
                fixtures.status_payload("FAILED", refund_reason="SWAP_FAILED", correlation_id=prepared2.quote.quote_id)
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
