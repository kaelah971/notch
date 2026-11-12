"""Live local HTTP smoke test for the S6 API against NEAR testnet data.

Starts the real API on an ephemeral localhost port, calls frontend routes,
asserts the two actual completed historical replay markets, and writes a compact
evidence JSON. No transaction is signed or broadcast.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.web_api.cli import build_default_app
from services.web_api.config import WebAPIConfig
from services.web_api.server import serve_in_thread


OUT = Path("docs/evidence/s6_live_smoke_20261112.json")


def call(base: str, method: str, path: str, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> int:
    app = build_default_app(WebAPIConfig(port=0))
    server, thread = serve_in_thread(app, host="127.0.0.1", port=0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    evidence: dict = {
        "schema_version": "notch.s6.live-smoke/1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": base,
        "network": "testnet",
        "endpoints": {},
        "assertions": {},
    }
    try:
        status, health = call(base, "GET", "/api/health")
        evidence["endpoints"]["health"] = {"status": status, "body": health}
        assert status == 200 and health["data"]["status"] == "ok"

        status, trends = call(base, "GET", "/api/trends")
        evidence["endpoints"]["trends"] = {
            "status": status,
            "count": trends["meta"]["count"],
            "first": trends["data"][:1],
        }
        assert status == 200 and trends["meta"]["count"] >= 2
        candidate_id = trends["data"][0]["candidate_id"]

        status, trend_detail = call(base, "GET", f"/api/trends/{candidate_id}")
        evidence["endpoints"]["trend_detail"] = {
            "status": status,
            "candidate_id": candidate_id,
            "title": trend_detail["data"]["title"],
        }
        assert status == 200

        status, trend_brief = call(base, "GET", f"/api/trends/{candidate_id}/brief")
        evidence["endpoints"]["trend_brief"] = {
            "status": status,
            "brief_id": trend_brief["data"]["brief_id"],
            "generation_status": trend_brief["data"]["generation_status"],
        }
        assert status == 200
        assert trend_brief["data"]["generation_status"] == "NON_AI_FALLBACK"

        status, markets = call(base, "GET", "/api/markets")
        rows = markets["data"]
        evidence["endpoints"]["markets"] = {
            "status": status,
            "count": markets["meta"]["count"],
            "markets": [
                {
                    "market_id": item["market_id"],
                    "mode": item["mode"],
                    "status": item["status"],
                    "display_status": item["display_status"],
                    "is_historical_replay": item["is_historical_replay"],
                    "winning_choice": item["winning_choice"],
                }
                for item in rows
            ],
        }
        historical = [item for item in rows if item["is_historical_replay"]]
        future = [item for item in rows if item["is_future_prediction"]]
        assert status == 200 and len(rows) == 3
        assert len(historical) == 2
        assert all(item["status"] == "resolved" for item in historical)
        assert len(future) == 1
        assert future[0]["status"] == "open"
        assert future[0]["entries_open"] is True
        assert future[0]["is_historical_replay"] is False

        market_id = historical[0]["market_id"]
        future_id = future[0]["market_id"]
        status, market_detail = call(base, "GET", f"/api/markets/{market_id}")
        evidence["endpoints"]["market_detail"] = {
            "status": status,
            "market_id": market_id,
            "status_value": market_detail["data"]["status"],
            "winning_choice": market_detail["data"]["winning_choice"],
            "evidence_verified": market_detail["data"]["evidence_verified"],
        }
        assert status == 200 and market_detail["data"]["status"] == "resolved"

        status, market_evidence = call(base, "GET", f"/api/markets/{market_id}/evidence")
        evidence["endpoints"]["market_evidence"] = {
            "status": status,
            "verified": market_evidence["data"]["verified"],
            "rule_hash": market_evidence["data"]["rule_record"]["rule_hash"],
            "evidence_digest": market_evidence["data"]["evidence_digest"],
        }
        assert status == 200 and market_evidence["data"]["verified"] is True

        status, market_brief = call(base, "GET", f"/api/markets/{market_id}/brief")
        brief = market_brief["data"]["brief"]
        evidence["endpoints"]["market_brief"] = {
            "status": status,
            "brief_id": brief["brief_id"],
            "generation_status": brief["generation_status"],
            "resolution_outcome": brief["resolution"]["outcome"],
        }
        assert status == 200
        assert brief["generation_status"] == "NON_AI_FALLBACK"
        assert brief["resolution"]["outcome"] == "UP"

        status, closed_entry = call(
            base,
            "POST",
            f"/api/markets/{market_id}/entry-intent",
            {"account_id": "notch-dev.testnet", "side": 0, "stake": "1000000"},
        )
        evidence["endpoints"]["closed_market_entry"] = {
            "status": status,
            "error": closed_entry["error"],
        }
        assert status == 409 and closed_entry["error"]["code"] == "MARKET_NOT_OPEN"

        status, open_entry = call(
            base,
            "POST",
            f"/api/markets/{future_id}/entry-intent",
            {"account_id": "notch-dev.testnet", "side": 0, "stake": "1000000"},
        )
        evidence["endpoints"]["open_market_entry"] = {
            "status": status,
            "market_id": future_id,
            "intent": open_entry.get("data"),
        }
        assert status == 200
        assert open_entry["data"]["signed"] is False
        assert open_entry["data"]["broadcast"] is False
        assert open_entry["data"]["args"]["amount"] == "1000000"
        assert json.loads(open_entry["data"]["args"]["msg"])["market_id"] == future_id

        status, brief_status = call(base, "GET", "/api/briefs/status")
        evidence["endpoints"]["briefs_status"] = {"status": status, "body": brief_status}
        assert status == 200 and brief_status["data"]["key_present"] is False
        assert brief_status["data"]["model_verified"] is True

        status, balances = call(base, "GET", "/api/wallets/notch-dev.testnet/balances")
        usdc = next(t for t in balances["data"]["tokens"] if t["symbol"] == "USDC")
        evidence["endpoints"]["wallet_balances"] = {
            "status": status,
            "account_id": balances["data"]["account_id"],
            "usdc_balance": usdc["balance"],
            "usdc_decimals": usdc["decimals"],
            "collateral_ready": balances["data"]["collateral"]["ready"],
        }
        assert status == 200 and usdc["balance"] == "101998769"
        assert balances["data"]["collateral"]["ready"] is True

        status, positions = call(base, "GET", "/api/wallets/notch-dev.testnet/positions")
        evidence["endpoints"]["wallet_positions"] = {
            "status": status,
            "count": positions["meta"]["count"],
            "positions": positions["data"],
        }
        assert status == 200 and positions["meta"]["count"] == 2

        status, funding_tokens = call(base, "GET", "/api/funding/tokens")
        evidence["endpoints"]["funding_tokens"] = {
            "status": status,
            "token_count": len(funding_tokens["data"]["tokens"]),
            "route_count": len(funding_tokens["data"]["routes"]),
        }
        assert status == 200 and len(funding_tokens["data"]["tokens"]) == 31

        status, readiness = call(
            base, "GET", "/api/funding/readiness?account_id=notch-dev.testnet"
        )
        evidence["endpoints"]["funding_readiness"] = {"status": status, "body": readiness}
        assert status == 200 and readiness["data"]["ready"] is True

        status, quote = call(
            base,
            "POST",
            "/api/funding/quote",
            {
                "source_asset": "nep141:usdt.tidepool-sandbox.testnet",
                "amount": "1000000",
                "recipient": "notch-dev.testnet",
                "dry": True,
                "deadline_minutes": 30,
            },
        )
        quote_id = quote["data"]["quote"]["quote_id"]
        evidence["endpoints"]["funding_quote"] = {
            "status": status,
            "quote_id": quote_id,
            "state": quote["data"]["quote"]["state"],
            "dry": True,
        }
        assert status == 200 and quote_id

        status, funding_status = call(base, "GET", f"/api/funding/status/{quote_id}")
        evidence["endpoints"]["funding_status"] = {
            "status": status,
            "state": funding_status["data"]["state"],
        }
        assert status == 200

        evidence["assertions"] = {
            "actual_markets": 3,
            "historical_replays": 2,
            "future_open_markets": 1,
            "evidence_verified": True,
            "deterministic_brief": True,
            "closed_entry_rejected": True,
            "open_entry_prepared": True,
            "wallet_usdc": "101998769",
            "positions": 2,
            "funding_ready": True,
            "live_ai_calls": 0,
            "signed_transactions": 0,
            "broadcast_transactions": 0,
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(evidence["assertions"], indent=2))
        print(f"wrote {OUT}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
