"""HTTP API integration tests with deterministic fakes."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.client import HTTPConnection
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from services.intents.validation import ValidationError
from services.near_ai.client import NearAIError
from services.web_api.app import RateLimiter, WebAPI
from services.web_api.chain import ChainReadError
from services.web_api.config import WebAPIConfig
from services.web_api.server import serve_in_thread


NOW_NS = 1_794_476_000_000_000_000
OPEN_ID = "s3b-future-test-open"
RESOLVED_ID = "s3b-replay-test-resolved"


class FakeChain:
    def __init__(self):
        self.fail = False
        self.config = {
            "collateral_token": "usdc.tidepool-sandbox.testnet",
            "min_entry_amount": "1000000",
            "entries_paused": False,
            "fee_bps": 0,
            "market_count": 2,
        }
        self.markets = {
            OPEN_ID: {
                "market_id": OPEN_ID,
                "mode": "trend_trading",
                "question": "FORECAST (not a replay): test future market",
                "choices": ["UP", "DOWN"],
                "source_id": "wikimedia-pageviews-v1",
                "rule_hash": "sha256:" + "a" * 64,
                "status": "open",
                "entries_open": True,
                "entries_paused": False,
                "open_at": str(NOW_NS - 1000),
                "close_at": str(NOW_NS + 86_400_000_000_000),
                "resolve_after": str(NOW_NS + 172_800_000_000_000),
                "totals": ["0", "0"],
                "escrow_total": "0",
                "paid_total": "0",
                "unclaimed_reserve": "0",
                "winning_outcome": None,
                "winning_choice": None,
                "evidence_hash": None,
                "resolution_kind": None,
                "created_at": str(NOW_NS - 2000),
                "resolved_at": None,
                "battle": None,
            },
            RESOLVED_ID: {
                "market_id": RESOLVED_ID,
                "mode": "trend_trading",
                "question": "HISTORICAL REPLAY (not a forecast): test resolved market",
                "choices": ["UP", "DOWN"],
                "source_id": "wikimedia-pageviews-v1",
                "rule_hash": "sha256:" + "b" * 64,
                "status": "resolved",
                "entries_open": False,
                "entries_paused": False,
                "open_at": str(NOW_NS - 200_000_000_000_000),
                "close_at": str(NOW_NS - 100_000_000_000_000),
                "resolve_after": str(NOW_NS - 50_000_000_000_000),
                "totals": ["1000000", "0"],
                "escrow_total": "1000000",
                "paid_total": "1000000",
                "unclaimed_reserve": "0",
                "winning_outcome": 0,
                "winning_choice": "UP",
                "evidence_hash": "sha256:" + "c" * 64,
                "resolution_kind": "winning_outcome",
                "created_at": str(NOW_NS - 300_000_000_000_000),
                "resolved_at": str(NOW_NS - 40_000_000_000_000),
                "battle": None,
            },
        }

    def now_ns(self):
        return NOW_NS

    def get_contract_config(self):
        return dict(self.config)

    def get_market_count(self):
        if self.fail:
            raise ChainReadError("rpc unavailable")
        return len(self.markets)

    def list_markets(self):
        if self.fail:
            raise ChainReadError("rpc unavailable")
        return list(self.markets.values())

    def get_market(self, market_id):
        return self.markets.get(market_id)

    def get_market_totals(self, market_id):
        market = self.markets.get(market_id)
        return {
            "market_id": market_id,
            "status": market["status"],
            "totals": market["totals"],
            "escrow_total": market["escrow_total"],
            "paid_total": market["paid_total"],
            "unclaimed_reserve": market["unclaimed_reserve"],
        } if market else None

    def get_position(self, market_id, account_id):
        if market_id == RESOLVED_ID and account_id == "notch-dev.testnet":
            return {
                "market_id": market_id,
                "account_id": account_id,
                "stakes": ["1000000", "0"],
                "total_stake": "1000000",
                "claimed_total": "1000000",
                "pending_amount": "0",
                "claimable": "0",
                "claim_state": "claimed",
            }
        return None

    def ft_metadata(self, contract):
        return {
            "decimals": 6,
            "symbol": "USDC" if "usdc" in contract else "USDT",
            "name": "Test " + ("USDC" if "usdc" in contract else "USDT"),
        }

    def ft_balance(self, contract, account_id):
        return "101998769" if "usdc" in contract else "98000000"

    def storage_balance(self, contract, account_id):
        return {"total": "1250000000000000000000", "available": "0"}

    def native_balance(self, account_id):
        return "2984597446695632999999997"


class FakeRadar:
    def __init__(self):
        self.candidates = [
            {
                "candidate_id": "cand_test_nvidia",
                "title": "Nvidia",
                "canonical_topic_id": "entity:nvidia",
                "category": "AI & Technology",
                "observed_at": "2026-11-12T00:00:00Z",
                "discovery_signals": {"score": 85, "source_count": 2, "sources": ["wikimedia"]},
                "source_urls": ["https://en.wikipedia.org/wiki/Nvidia"],
                "settlement_coverage": {
                    "window_start": "2026-11-04",
                    "window_end": "2026-11-10",
                    "min_views": 4112,
                    "mean_views": 43298,
                    "daily_views": [
                        {"date": "2026-11-04", "views": 4112},
                        {"date": "2026-11-05", "views": 4743},
                        {"date": "2026-11-06", "views": 4626},
                        {"date": "2026-11-07", "views": 5535},
                        {"date": "2026-11-08", "views": 17886},
                        {"date": "2026-11-09", "views": 142333},
                        {"date": "2026-11-10", "views": 123851},
                    ],
                    "raw_hashes": ["sha256:test-pageviews"],
                },
                "discovery_evidence": [],
            }
        ]

    def list_candidates(self, limit=50):
        return list(self.candidates)

    def get_candidate(self, candidate_id):
        return next((c for c in self.candidates if c["candidate_id"] == candidate_id), None)

    def summary(self, candidate, now=None):
        return {
            "candidate_id": candidate["candidate_id"],
            "title": candidate["title"],
            "score": 85,
            "source_count": 2,
        }

    def detail(self, candidate, now=None):
        return {**self.summary(candidate), "candidate": candidate, "evidence": []}


class FakeOracle:
    def __init__(self):
        self.rule = {
            "rule_hash": "sha256:" + "a" * 64,
            "market_id": OPEN_ID,
            "mode": "trend_trading",
            "status": "APPROVED",
            "created_at": "2026-11-12T00:00:00Z",
            "rule": {
                "market_id": OPEN_ID,
                "mode": "trend_trading",
                "observation": {"replay": False},
                "topics": [{"article_title": "Bitcoin"}],
            },
        }
        self.evidence = {
            "market_id": OPEN_ID,
            "rule_hash": "sha256:" + "a" * 64,
            "evidence_digest": "sha256:" + "c" * 64,
            "outcome": "UP",
        }

    def find(self, market_id):
        rule = json.loads(json.dumps(self.rule))
        if market_id == RESOLVED_ID:
            rule["rule"]["observation"] = {"replay": True}
        return rule, self.evidence

    def find_rule(self, market_id):
        return json.loads(json.dumps(self.rule))

    def matching_historical_context(self, rule, limit=4):
        return []

    def published_topic_matches(self, market_ids):
        return {}

    def verify(self, market_id):
        return {
            "market_id": market_id,
            "rule": self.rule["rule"],
            "evidence": self.evidence,
            "verified": True,
            "verification": {"valid": True, "reasons": []},
        }


class FakeResult:
    def __init__(self, data):
        self.data = data
        self.inference = data.get("inference", {})
        self.provider = data.get("provider", "deterministic")
        self.cache_hit = bool(data.get("cache_hit", False))

    def to_dict(self):
        return self.data


class FakeBrief:
    def __init__(self):
        self.config = SimpleNamespace(
            key_present=False,
            model="z-ai/glm-5.3-flash",
            base_url="https://cloud-api.near.ai/v1",
        )
        self.store = SimpleNamespace(count=lambda: 3, close=lambda: None)

    def radar_brief(self, candidate_id, *, allow_ai=False):
        return FakeResult(
            {
                "brief_id": "brief_test",
                "generation_status": "NON_AI_FALLBACK",
                "provider": "deterministic",
                "resolution": None,
            }
        )

    def market_brief_from_records(self, rule, evidence, *, allow_ai=False):
        return FakeResult(
            {
                "brief_id": "brief_market_test",
                "generation_status": "NON_AI_FALLBACK",
                "provider": "deterministic",
                "resolution": {"outcome": "UP", "rule_hash": rule["rule_hash"]},
            }
        )

    def market_research_from_records(self, rule, evidence, *, attention_snapshots, historical_context, allow_ai=True):
        return FakeResult(
            {
                "brief_id": "brief_research_test",
                "generation_status": "NON_AI_FALLBACK",
                "provider": "deterministic",
                "inference": {"source_ids": ["market:test:rule"], "input_observation_cutoff": None},
                "research": {"supporting_up": [], "supporting_down": []},
            }
        )

    def status(self):
        return {
            "key_present": False,
            "model_verified": True,
            "configured_model": "z-ai/glm-5.3-flash",
            "catalog_count": 63,
        }


class FakeCouncil:
    def __init__(self):
        self.last = None

    def close(self):
        return None

    def get_latest(self, market_id):
        return self.last

    def generate_from_records(self, rule, evidence, *, attention_snapshots, historical_context, force=False, allow_ai=True):
        self.last = {
            "schema_version": "notch.research-council/1",
            "council_id": "council_test",
            "market_id": rule["market_id"],
            "generation_mode": "DETERMINISTIC_EVIDENCE_LENSES",
            "ai_call_triggered": False,
            "cache_hit": False,
            "snapshot": {"snapshot_id": "snapshot_test", "snapshot_digest": "sha256:snapshot"},
            "roles": [],
            "disagreement": {"status": "UNRESOLVED", "records": []},
            "audit": {"audit_id": "audit_test", "execution_boundary": {"broadcast": False}},
            "execution": {"wallet_action": False, "signature_requested": False, "broadcast": False},
        }
        return self.last


class FakeToken:
    def __init__(self, symbol):
        self.symbol = symbol

    def to_dict(self):
        return {"symbol": self.symbol, "asset_id": f"nep141:{self.symbol.lower()}.testnet"}


class FakeRoute:
    def to_dict(self):
        return {"label": "USDT -> USDC"}


class FakeFunding:
    def __init__(self):
        self.config = SimpleNamespace(
            data_dir="var/intents",
            destination_asset="nep141:usdc.tidepool-sandbox.testnet",
            api_key="secret-key",
        )
        self.store = SimpleNamespace(close=lambda: None)

    def discover_tokens(self):
        return [FakeToken("USDC"), FakeToken("USDT")]

    def supported_routes(self):
        return [FakeRoute()]

    def dry_quote(self, **kwargs):
        if kwargs.get("amount") == "invalid":
            raise ValidationError("INVALID_AMOUNT", "amount must be an integer string", field="amount")
        return FakeResult({"quote": {"quote_id": "q1", "state": "QUOTED"}})

    def prepare_swap(self, **kwargs):
        return self.dry_quote(**kwargs)

    def get_quote(self, quote_id):
        return {"quote_id": quote_id}

    def quote_summary(self, quote):
        return {"quote": quote, "state": "AWAITING_DEPOSIT"}

    def refresh_status(self, quote_id, max_attempts=1):
        return {"quote_id": quote_id}

    def get_available_collateral(self, account):
        return {"account": account, "ready": True, "balance": "101998769"}


def make_app(*, rate_limit=1000):
    config = WebAPIConfig(
        radar_db="README.md",
        oracle_db_paths=("README.md",),
        general_rate_limit_per_minute=rate_limit,
        quote_rate_limit_per_minute=rate_limit,
        entry_rate_limit_per_minute=rate_limit,
    )
    return WebAPI(
        config=config,
        chain=FakeChain(),
        radar=FakeRadar(),
        oracle=FakeOracle(),
        brief_service=FakeBrief(),
        funding_service=FakeFunding(),
        council_service=FakeCouncil(),
        rate_limiter=RateLimiter(),
    )


class APITests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.client = "test-client"

    def tearDown(self):
        self.app.close()

    def call(self, method, path, body=None):
        parsed = urlparse(path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        return self.app.handle(method, parsed.path, query, body, client=self.client)

    def test_health(self):
        status, payload = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertTrue(payload["data"]["checks"]["near_rpc"]["ok"])

    def test_trends_and_detail(self):
        status, payload = self.call("GET", "/api/trends")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["count"], 1)
        status, payload = self.call("GET", "/api/trends/cand_test_nvidia")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["title"], "Nvidia")

    def test_scout_is_source_backed_and_bounded(self):
        status, payload = self.call("GET", "/api/scout?direction=rising&limit=99")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["direction"], "RISING")
        self.assertEqual(payload["meta"]["source"], "wikimedia-pageviews-v1")
        self.assertEqual(len(payload["data"]), 1)
        item = payload["data"][0]
        self.assertEqual(item["topic"], "Nvidia")
        self.assertEqual(item["source"]["id"], "wikimedia-pageviews-v1")
        self.assertEqual(item["observation_window"]["sample_count"], 7)
        self.assertTrue(item["evidence_digest"].startswith("sha256:"))
        self.assertEqual(item["proposal"]["status"], "REVIEW_ONLY")
        self.assertFalse(item["proposal"]["published"])
        status, payload = self.call("GET", "/api/scout/cand_test_nvidia")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["candidate_id"], "cand_test_nvidia")

    def test_pulse_reports_unconfigured_coverage_explicitly(self):
        status, payload = self.call("GET", "/api/pulse?window=7d&refresh=false")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["coverage"]["status"], "not_configured")
        self.assertEqual(payload["data"]["metrics"]["successful_entries"], 0)
        status, payload = self.call("GET", "/api/pulse?window=2h")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_WINDOW")

    def test_trend_brief(self):
        status, payload = self.call("GET", "/api/trends/cand_test_nvidia/brief")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["generation_status"], "NON_AI_FALLBACK")
        self.assertFalse(payload["meta"]["ai_call_triggered"])

    def test_markets_and_detail(self):
        status, payload = self.call("GET", "/api/markets")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["count"], 2)
        historical = [item for item in payload["data"] if item["is_historical_replay"]]
        future = [item for item in payload["data"] if item["is_future_prediction"]]
        self.assertEqual(len(historical), 1)
        self.assertEqual(len(future), 1)
        self.assertFalse(historical[0]["is_future_prediction"])
        status, payload = self.call("GET", f"/api/markets/{RESOLVED_ID}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["status"], "resolved")
        self.assertEqual(payload["data"]["winning_choice"], "UP")

    def test_market_evidence_and_brief(self):
        status, payload = self.call("GET", f"/api/markets/{OPEN_ID}/evidence")
        self.assertEqual(status, 200)
        self.assertTrue(payload["data"]["verified"])
        status, payload = self.call("GET", f"/api/markets/{OPEN_ID}/brief")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["brief"]["generation_status"], "NON_AI_FALLBACK")
        self.assertFalse(payload["meta"]["ai_call_triggered"])
        status, payload = self.call("POST", f"/api/markets/{OPEN_ID}/research", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["brief"]["brief_id"], "brief_research_test")
        self.assertFalse(payload["meta"]["ai_call_triggered"])
        self.assertEqual(payload["meta"]["generation_mode"], "explicit_research_request")

    def test_market_research_council_is_read_only_and_snapshot_bound(self):
        status, payload = self.call("POST", f"/api/markets/{OPEN_ID}/council", {"allow_ai": False})
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["council"]["generation_mode"], "DETERMINISTIC_EVIDENCE_LENSES")
        self.assertFalse(payload["data"]["council"]["execution"]["broadcast"])
        self.assertEqual(payload["meta"]["snapshot_id"], "snapshot_test")
        status, payload = self.call("GET", f"/api/markets/{OPEN_ID}/council")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["council"]["council_id"], "council_test")

    def test_market_research_provider_error_is_safe(self):
        def fail(*args, **kwargs):
            raise NearAIError("provider throttled", status=429, code="RATE_LIMITED", retryable=True)

        self.app.brief_service.market_research_from_records = fail
        status, payload = self.call("POST", f"/api/markets/{OPEN_ID}/research", {})
        self.assertEqual(status, 429)
        self.assertEqual(payload["error"]["code"], "RATE_LIMITED")
        self.assertTrue(payload["error"]["details"]["retryable"])
        self.assertNotIn("Authorization", json.dumps(payload))

    def test_wallet_balances_base_units(self):
        status, payload = self.call("GET", "/api/wallets/notch-dev.testnet/balances")
        self.assertEqual(status, 200)
        usdc = payload["data"]["tokens"][0]
        self.assertEqual(usdc["balance"], "101998769")
        self.assertEqual(usdc["decimals"], 6)
        self.assertIsInstance(usdc["balance"], str)
        self.assertEqual(payload["data"]["collateral"]["ready"], True)

    def test_wallet_positions(self):
        status, payload = self.call("GET", "/api/wallets/notch-dev.testnet/positions")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["data"][0]["claim_state"], "claimed")
        self.assertEqual(payload["data"][0]["prediction_status"], "CORRECT")
        self.assertEqual(payload["data"][0]["prediction_choice"], "UP")
        self.assertEqual(payload["data"][0]["prediction_choices"], ["UP"])
        self.assertEqual(payload["data"][0]["evidence_hash"], "sha256:" + "c" * 64)

    def test_funding_tokens_readiness_and_status(self):
        status, payload = self.call("GET", "/api/funding/tokens")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["data"]["tokens"]), 2)
        status, payload = self.call("GET", "/api/funding/readiness?account_id=notch-dev.testnet")
        self.assertEqual(status, 200)
        self.assertTrue(payload["data"]["ready"])
        status, payload = self.call("GET", "/api/funding/status/q1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["state"], "AWAITING_DEPOSIT")

    def test_funding_quote_validation(self):
        status, payload = self.call(
            "POST",
            "/api/funding/quote",
            {
                "source_asset": "nep141:usdt.tidepool-sandbox.testnet",
                "amount": "invalid",
                "recipient": "notch-dev.testnet",
                "dry": True,
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_AMOUNT")

    def test_entry_intent_preparation(self):
        status, payload = self.call(
            "POST",
            f"/api/markets/{OPEN_ID}/entry-intent",
            {"account_id": "notch-dev.testnet", "side": 0, "stake": "1000000"},
        )
        self.assertEqual(status, 200)
        intent = payload["data"]
        self.assertEqual(intent["receiver"], "usdc.tidepool-sandbox.testnet")
        self.assertEqual(intent["method"], "ft_transfer_call")
        self.assertEqual(intent["args"]["amount"], "1000000")
        self.assertEqual(intent["args"]["receiver_id"], "market.notch-dev.testnet")
        self.assertEqual(json.loads(intent["args"]["msg"])["outcome"], 0)
        self.assertFalse(intent["signed"])
        self.assertFalse(intent["broadcast"])

    def test_closed_market_rejected(self):
        status, payload = self.call(
            "POST",
            f"/api/markets/{RESOLVED_ID}/entry-intent",
            {"account_id": "notch-dev.testnet", "side": 0, "stake": "1000000"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "MARKET_NOT_OPEN")

    def test_invalid_market_id(self):
        status, payload = self.call("GET", "/api/markets/unknown")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "MARKET_NOT_FOUND")

    def test_invalid_amount(self):
        status, payload = self.call(
            "POST",
            f"/api/markets/{OPEN_ID}/entry-intent",
            {"account_id": "notch-dev.testnet", "side": 0, "stake": "0"},
        )
        self.assertEqual(status, 400)

    def test_provider_failure(self):
        self.app.chain.fail = True
        status, payload = self.call("GET", "/api/markets")
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"]["code"], "DEPENDENCY_UNAVAILABLE")

    def test_rate_limit(self):
        app = make_app(rate_limit=1)
        try:
            status, _ = app.handle("GET", "/api/health", {}, None, client="rate-test")
            self.assertEqual(status, 200)
            status, payload = app.handle("GET", "/api/health", {}, None, client="rate-test")
            self.assertEqual(status, 429)
            self.assertEqual(payload["error"]["code"], "RATE_LIMITED")
        finally:
            app.close()

    def test_no_secret_in_response(self):
        status, payload = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        text = json.dumps(payload)
        self.assertNotIn("secret-key", text)
        self.assertNotIn("NEAR_AI_KEY", text)

    def test_http_cors_and_json(self):
        app = make_app()
        server, thread = serve_in_thread(app, host="127.0.0.1", port=0)
        try:
            port = server.server_address[1]
            conn = HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("OPTIONS", "/api/health", headers={"Origin": "http://localhost:3000"})
            resp = conn.getresponse()
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "http://localhost:3000")
            resp.read()
            conn.request("GET", "/api/health", headers={"Origin": "http://evil.example"})
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))
            resp.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
            app.close()


if __name__ == "__main__":
    unittest.main()
