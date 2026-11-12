"""Tests for the Tidepool HTTP client boundary."""

from __future__ import annotations

import json
import unittest

from services.intents.client import (
    RateLimiter,
    TidepoolAPIError,
    TidepoolClient,
    TidepoolResponseError,
    TidepoolTransportError,
)
from services.intents.models import QuoteRequest
from services.intents.tests import fixtures


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, params, body, headers, timeout):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "body": body,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected provider call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _json(data):
    return 200, {}, json.dumps(data)


def _client(transport, **kwargs):
    return TidepoolClient(
        transport=transport,
        rate_limiter=RateLimiter(interval_seconds=0),
        sleep=lambda _: None,
        **kwargs,
    )


class ClientTests(unittest.TestCase):
    def test_tokens_parse_and_query(self):
        transport = FakeTransport([_json(fixtures.TOKENS)])
        client = _client(transport, api_key="test-key")
        tokens = client.get_tokens()
        self.assertEqual(len(tokens), len(fixtures.TOKENS))
        self.assertEqual(tokens[1].symbol, "USDT")
        self.assertEqual(tokens[1].decimals, 6)
        self.assertEqual(transport.calls[0]["method"], "GET")
        self.assertTrue(transport.calls[0]["url"].endswith("/v0/tokens"))
        self.assertEqual(transport.calls[0]["headers"]["X-API-Key"], "test-key")

    def test_quote_sends_exact_request_and_parses(self):
        transport = FakeTransport([_json(fixtures.quote_response(dry=True))])
        client = _client(transport)
        request = QuoteRequest(
            dry=True,
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
        )
        response = client.quote(request)
        self.assertEqual(response.correlation_id, "quote-test-1")
        self.assertEqual(response.quote.amount_out, "996968")
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertEqual(transport.calls[0]["body"]["originAsset"], request.origin_asset)
        self.assertEqual(transport.calls[0]["body"]["amount"], "1000000")
        self.assertNotIn("X-API-Key", transport.calls[0]["headers"])

    def test_status_query_and_memo(self):
        transport = FakeTransport([_json(fixtures.status_payload("PENDING_DEPOSIT"))])
        client = _client(transport)
        result = client.get_status(deposit_address=fixtures.DEPOSIT_ADDRESS, memo="memo-1")
        self.assertEqual(result.status, "PENDING_DEPOSIT")
        self.assertEqual(
            transport.calls[0]["params"],
            {"depositAddress": fixtures.DEPOSIT_ADDRESS, "depositMemo": "memo-1"},
        )

    def test_submit_deposit_body(self):
        transport = FakeTransport([_json(fixtures.status_payload("KNOWN_DEPOSIT_TX"))])
        client = _client(transport)
        result = client.submit_deposit(
            tx_hash="tx-1",
            deposit_address=fixtures.DEPOSIT_ADDRESS,
            near_sender_account="notch-dev.testnet",
        )
        self.assertEqual(result.status, "KNOWN_DEPOSIT_TX")
        self.assertEqual(
            transport.calls[0]["body"],
            {
                "txHash": "tx-1",
                "depositAddress": fixtures.DEPOSIT_ADDRESS,
                "nearSenderAccount": "notch-dev.testnet",
            },
        )

    def test_429_retries_with_bounded_backoff(self):
        transport = FakeTransport(
            [
                (429, {"retry-after": "0"}, json.dumps({"message": "rate limited"})),
                _json(fixtures.TOKENS),
            ]
        )
        sleeps = []
        client = TidepoolClient(
            transport=transport,
            max_retries=1,
            rate_limiter=RateLimiter(interval_seconds=0),
            sleep=sleeps.append,
        )
        tokens = client.get_tokens()
        self.assertEqual(len(tokens), len(fixtures.TOKENS))
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(sleeps, [0.0])

    def test_400_is_not_retried(self):
        transport = FakeTransport(
            [(400, {}, json.dumps({"message": "bad route", "hint": "use a testnet asset"}))]
        )
        client = _client(transport, max_retries=2)
        with self.assertRaises(TidepoolAPIError) as ctx:
            client.get_tokens()
        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("bad route", str(ctx.exception))
        self.assertEqual(len(transport.calls), 1)

    def test_transport_error_retries_get_then_raises(self):
        transport = FakeTransport(
            [
                TidepoolTransportError("timeout", retryable=True, path="/v0/tokens"),
                TidepoolTransportError("timeout", retryable=True, path="/v0/tokens"),
            ]
        )
        client = _client(transport, max_retries=1)
        with self.assertRaises(TidepoolTransportError):
            client.get_tokens()
        self.assertEqual(len(transport.calls), 2)

    def test_invalid_json_is_response_error(self):
        transport = FakeTransport([(200, {}, "not-json")])
        client = _client(transport)
        with self.assertRaises(TidepoolResponseError):
            client.get_tokens()

    def test_include_ondo_query(self):
        transport = FakeTransport([_json(fixtures.TOKENS)])
        client = _client(transport)
        client.get_tokens(include_ondo=True)
        self.assertEqual(transport.calls[0]["params"], {"ondoTokens": "1"})


if __name__ == "__main__":
    unittest.main()
