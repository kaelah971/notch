"""Phase 7B manual Base Sepolia funding and provider-boundary tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.intents.balance import NearRpcClient
from services.intents.config import IntentsConfig
from services.intents.models import QuoteResponse, StatusResponse, Token
from services.intents.service import IntentsFundingService
from services.intents.signature import verify_ed25519_signature
from services.intents.store import DuplicateDepositError, FundingStore
from services.intents.tests import fixtures
from services.intents.validation import ValidationError, select_route, validate_quote_response

BASE_ASSET = "nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet"
BASE_REFUND = "0x1111111111111111111111111111111111111111"
BASE_DEPOSIT = "0x2222222222222222222222222222222222222222"


class ExternalClient:
    def __init__(self) -> None:
        self.tokens = [Token.from_provider(item) for item in fixtures.TOKENS]
        self.statuses: list[StatusResponse] = []
        self.submit_calls = 0

    def get_tokens(self, *, include_ondo: bool = False):
        return list(self.tokens)

    def quote(self, request):
        payload = fixtures.quote_response(
            dry=request.dry,
            deposit_type=request.deposit_type,
            amount=request.amount,
        )
        payload["correlationId"] = "base-quote-test"
        payload["quoteRequest"].update(
            {
                "originAsset": BASE_ASSET,
                "refundTo": BASE_REFUND,
                "refundType": "ORIGIN_CHAIN",
                "recipient": request.recipient,
                "deadline": request.deadline,
            }
        )
        if not request.dry:
            payload["quote"]["depositAddress"] = BASE_DEPOSIT
            payload["quote"]["deadline"] = request.deadline
            payload["quote"]["timeWhenInactive"] = request.deadline
        return QuoteResponse.from_provider(payload)

    def get_status(self, *, deposit_address, memo=None):
        if not self.statuses:
            raise AssertionError("no status fixture queued")
        return self.statuses.pop(0)

    def submit_deposit(self, *, tx_hash, deposit_address, near_sender_account=None, memo=None):
        self.submit_calls += 1
        if not self.statuses:
            raise AssertionError("no submit status fixture queued")
        return self.statuses.pop(0)


class FakeReader:
    def __init__(self) -> None:
        self.balance = 100_000_000

    def ft_balance_of(self, contract, account):
        return self.balance

    def storage_balance_of(self, contract, account):
        return {"total": "1250000000000000000000", "available": "0"}


class Phase7BFundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FundingStore(Path(self.tmp.name) / "funding.sqlite3")
        self.client = ExternalClient()
        self.service = IntentsFundingService(
            client=self.client,
            store=self.store,
            config=IntentsConfig(
                data_dir=self.tmp.name,
                verify_quote_signatures=False,
            ),
            reader=FakeReader(),
            now_fn=lambda: fixtures.NOW,
            sleep=lambda _: None,
        )

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def prepare(self):
        return self.service.prepare_swap(
            source_asset=BASE_ASSET,
            source_chain="base",
            amount="1000000",
            recipient="notch-dev.testnet",
            refund_to=BASE_REFUND,
            deposit_type="ORIGIN_CHAIN",
        )

    def test_quote_signature_crypto_vector_and_invalid_signature(self) -> None:
        public_key = "ed25519:FVen3X669xLzsi6N2V91DoiyzHzg1uAgqiT8jZ9nS96Z"
        signature = "ed25519:5awYiUvGiDFA33EJjj4TXJG44a5afJc8QjWRpGgQiu6b23jCr7yndW2fmp9ujwqJVe32J456wV3VF78Asb1obnTc"
        self.assertTrue(verify_ed25519_signature(public_key, signature, b""))
        self.assertFalse(verify_ed25519_signature(public_key, signature[:-1] + "A", b""))

    def test_live_quote_requires_a_verifiable_signature_in_production_mode(self) -> None:
        tokens = self.client.get_tokens()
        route = select_route(tokens, BASE_ASSET, self.service.config, source_chain="base")
        response = QuoteResponse.from_provider(fixtures.quote_response(dry=False, deposit_type="ORIGIN_CHAIN"))
        with self.assertRaisesRegex(ValidationError, "does not verify"):
            validate_quote_response(
                response,
                response.quote_request,
                route,
                self.service.config,
                now=fixtures.NOW,
                verify_signature=True,
            )

    def test_external_live_quote_is_manual_only_and_preserves_exact_route(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.quote.source_asset, BASE_ASSET)
        self.assertEqual(prepared.quote.source_chain, "base")
        self.assertEqual(prepared.instructions.provider_deposit_address, BASE_DEPOSIT)
        self.assertTrue(prepared.instructions.supported)
        self.assertTrue(prepared.instructions.manual_only)
        self.assertEqual(prepared.instructions.steps, [])
        self.assertFalse(prepared.quote.deposit_submitted)

    def test_base_tx_hash_is_validated_and_duplicate_submission_is_idempotent(self) -> None:
        prepared = self.prepare()
        with self.assertRaisesRegex(ValidationError, "not valid for source chain base"):
            self.service.record_deposit(prepared.quote.quote_id, "tx-not-base", submit=False)
        tx_hash = "0x" + "a" * 64
        first = self.service.record_deposit(prepared.quote.quote_id, tx_hash, submit=False)
        again = self.service.record_deposit(prepared.quote.quote_id, tx_hash, submit=False)
        self.assertEqual(first.deposit_tx_hash, again.deposit_tx_hash)
        with self.assertRaises(DuplicateDepositError):
            self.service.record_deposit(prepared.quote.quote_id, "0x" + "b" * 64, submit=False)

    def test_status_identity_mismatch_never_claims_destination_success(self) -> None:
        prepared = self.prepare()
        self.service.record_deposit(prepared.quote.quote_id, "0x" + "a" * 64)
        mismatched = StatusResponse.from_provider(fixtures.status_payload("SUCCESS"))
        self.client.statuses = [mismatched]
        result = self.service.refresh_status(prepared.quote.quote_id, max_attempts=1)
        self.assertEqual(result.state.value, "AWAITING_DEPOSIT")
        self.assertFalse(result.balance_verified)
        self.assertIn("does not match", result.last_error or "")


if __name__ == "__main__":
    unittest.main()
