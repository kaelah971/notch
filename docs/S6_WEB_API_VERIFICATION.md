# S6 — Frontend-ready web API verification

Date: 2026-11-12 (UTC)
Status: **BACKEND HTTP API IMPLEMENTED — APPROVED FUTURE MARKET CREATED AND VERIFIED — NO FRONTEND**
Network: NEAR testnet only.

## 1. Implementation and startup

The API is a small standard-library `http.server` application. FastAPI/uvicorn
were not installed, and no new framework dependency was added. Typed response
schemas live in `services/web_api/schemas.py`; the frontend contract is
`docs/FRONTEND_INTEGRATION_CONTRACT.md`.

Start locally:

```bash
python -m services.web_api --host 127.0.0.1 --port 8000
```

Then:

```bash
curl http://127.0.0.1:8000/api/health
```

The API reads the existing S3A Radar SQLite store, S3B Oracle stores, S4 funding
store/service, S5 brief service and the deployed `market.notch-dev.testnet`
contract. No new database, worker, queue or contract was added.

## 2. Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_API_HOST` | `127.0.0.1` | Bind host |
| `WEB_API_PORT` | `8000` | Bind port |
| `WEB_API_CORS_ORIGINS` | localhost:3000/5173 | Restrictive CORS allow-list |
| `WEB_API_MAX_BODY_BYTES` | `65536` | Request body cap |
| `WEB_API_RATE_LIMIT_PER_MINUTE` | `120` | General per-IP limit |
| `WEB_API_QUOTE_RATE_LIMIT_PER_MINUTE` | `10` | Funding quote limit |
| `WEB_API_ENTRY_RATE_LIMIT_PER_MINUTE` | `30` | Entry-intent limit |
| `WEB_API_REQUEST_TIMEOUT_SECONDS` | `15` | NEAR RPC timeout |
| `MARKET_CONTRACT` | `market.notch-dev.testnet` | Market contract |
| `COLLATERAL_TOKEN` | `usdc.tidepool-sandbox.testnet` | Collateral |
| `NEAR_RPC_URL` | `https://rpc.testnet.near.org` | RPC |
| `RADAR_DB_PATH` | `var/trend_radar_live_final/radar.sqlite3` | Radar store |
| `ORACLE_DB_PATHS` | short,long oracle stores | Oracle lookup order |
| `TIDEPOOL_*` | S4 defaults | Funding provider |
| `NEAR_AI_*` | S5 defaults | Brief catalog/status only |

No API key is required for public reads. The NEAR AI key and Tidepool API key
are never returned.

## 3. Routes

| Method | Route | Live result |
| --- | --- | --- |
| `GET` | `/api/health` | 200, `status: ok` |
| `GET` | `/api/trends` | 200, 11 eligible Radar candidates |
| `GET` | `/api/trends/{candidateId}` | 200, candidate + evidence |
| `GET` | `/api/trends/{candidateId}/brief` | 200, cached/deterministic brief |
| `GET` | `/api/markets` | 200, 3 actual onchain markets |
| `GET` | `/api/markets/{marketId}` | 200, onchain state + rule/evidence |
| `GET` | `/api/markets/{marketId}/evidence` | 200, rule + evidence; `verified:false` for unresolved future |
| `GET` | `/api/markets/{marketId}/brief` | 200, deterministic resolution + brief |
| `GET` | `/api/briefs/status` | 200, model catalog status, no secret |
| `GET` | `/api/funding/tokens` | 200, 31 live tokens |
| `POST` | `/api/funding/quote` | 200, dry/live quote; no transfer |
| `GET` | `/api/funding/status/{quoteId}` | 200, persisted quote state |
| `GET` | `/api/funding/readiness?account_id=...` | 200, actual USDC readiness |
| `GET` | `/api/wallets/{accountId}/balances` | 200, base units + decimals |
| `GET` | `/api/wallets/{accountId}/positions` | 200, onchain positions |
| `POST` | `/api/markets/{marketId}/entry-intent` | 409 for resolved markets; 200 unsigned intent for the open future market |

No public operator market-creation, resolution or admin endpoints exist.

## 4. Actual NEAR testnet data served

The live smoke test confirmed:

- **3 actual markets** from `market.notch-dev.testnet`:
  - `s3b-short-trend-nvidia-20261112T040029Z` — resolved `UP`
  - `s3b-short-battle-btc-chatgpt-20261112T040029Z` — resolved `Bitcoin`
  - `s3b-future-btc-20261116-20261123` — **open future prediction**, no outcome
- The two historical markets are marked `is_historical_replay: true` and
  `display_status: historical_replay_resolved`. The future market is
  `is_future_prediction: true`, `display_status: open_future`.
- **11 eligible Radar candidates**; Nvidia and Bitcoin are among them.
- **Wallet `notch-dev.testnet`**:
  - USDC: `101998769` base units (6 decimals)
  - USDT: `98000000` base units
  - USDC storage registered
  - 2 onchain positions, both `claimed`
- **S3B evidence** for the Nvidia market verified against the onchain rule hash.
- **S5 market brief** returned `NON_AI_FALLBACK` with deterministic `UP`
  resolution. No AI completion was called.
- **Tidepool** returned 31 live tokens and 5 NEAR→USDC routes.
- A dry 1-USDT quote returned `QUOTED`; no deposit/transfer.
- Resolved market entry returned `MARKET_NOT_OPEN` (409); the open future market
  returned a valid **unsigned** entry intent (200).

Live smoke evidence: `docs/evidence/s6_live_smoke_20261112.json`.

## 5. Live smoke output

Command:

```bash
python scripts/s6_live_smoke.py
```

Observed assertions:

```json
{
  "actual_markets": 3,
  "historical_replays": 2,
  "future_open_markets": 1,
  "evidence_verified": true,
  "deterministic_brief": true,
  "closed_entry_rejected": true,
  "open_entry_prepared": true,
  "wallet_usdc": "101998769",
  "positions": 2,
  "funding_ready": true,
  "live_ai_calls": 0,
  "signed_transactions": 0,
  "broadcast_transactions": 0
}
```

The smoke test starts a real local HTTP server on an ephemeral port and calls the
routes over HTTP. It does not use fixtures for the live chain data.

## 6. Tests

```bash
python -m unittest discover -s services/web_api/tests -t .
```

**17 API tests passed.**

Coverage:

- health;
- trend list/detail/brief;
- market list/detail/evidence/brief;
- historical replay flags and resolved status;
- wallet balances/base units/decimals;
- positions;
- funding tokens/readiness/status;
- quote validation;
- entry-intent preparation with exact `ft_transfer_call` args;
- closed-market rejection;
- invalid market ID/amount;
- provider failure;
- rate limiting;
- CORS;
- secret leakage prevention.

S5 tests: **36 passed** after adding a read-only no-AI test.
S4 tests: **47 passed** after adding thread-safe store access for the HTTP server.
The live smoke test additionally verified actual testnet data.

## 7. Wallet and transaction preparation

`POST /api/markets/{id}/entry-intent` returns:

```json
{
  "network": "testnet",
  "signer": "notch-dev.testnet",
  "receiver": "usdc.tidepool-sandbox.testnet",
  "method": "ft_transfer_call",
  "args": {
    "receiver_id": "market.notch-dev.testnet",
    "amount": "1000000",
    "msg": "{\"market_id\":\"...\",\"outcome\":0}"
  },
  "attached_deposit_yocto": "1",
  "gas_tgas": 100,
  "signed": false,
  "broadcast": false
}
```

Validation covers market existence/open state, entry deadline, collateral,
side, minimum stake, wallet balance and storage. The backend never signs or
broadcasts. Resolved markets return 409. The newly created future market returns
200 with an unsigned intent; no deposit or trade was made.

## 8. Future market — created and verified

The approved future market was created on NEAR testnet.

| Field | Value |
| --- | --- |
| Market ID | `s3b-future-btc-20261116-20261123` |
| Mode | `trend_trading` |
| Question | Bitcoin Wikimedia growth ≥ 23.00% on 2026-11-23 vs 2026-11-16 |
| Source | Wikimedia Pageviews, en.wikipedia.org, all-access/user |
| Baseline | 2026-11-16 UTC full day |
| Target | 2026-11-23 UTC full day |
| Entry close | `2026-11-15T23:59Z` |
| Resolution eligible | `2026-11-25T12:00Z` |
| Rule hash | `sha256:cd215ff8e2e09166607b04925464acc086b5c20b058de4fab2e8e07c633b789b` |
| Threshold | 2,300 bps |
| Minimum baseline | 1,000 views |
| Missing data | VOID / refund |
| Rule status | `APPROVED` locally |
| Creation tx | `ALVPQpRCwngtpLPtG94SrXb9Y4jogaFToTzvGusveXDA` |
| Explorer | <https://testnet.nearblocks.io/txns/ALVPQpRCwngtpLPtG94SrXb9Y4jogaFToTzvGusveXDA> |
| Onchain status | **`open`**, `entries_open: true`, totals `["0","0"]` |
| Outcome | **unresolved** (`winning_outcome: null`) |
| API | `is_future_prediction: true`, `display_status: open_future` |
| Evidence/brief | not available until the future observation/resolution |

The market is a genuine future prediction, not a historical replay. It was
created with the approved configuration; no deposit, trade, resolution or
additional market was made.

Evidence:

- `docs/evidence/s6_future_market_proposal.json`
- `docs/evidence/s6_future_market_create_args.json`
- `docs/evidence/s6_future_market_creation_20261112.json`
- `docs/evidence/s6_future_market_api_verification_20261112.json`

## 9. Security and limitations

- CORS is restricted to the configured local origins.
- Public requests are rate-limited in memory; limits reset on restart.
- Request bodies are capped at 64 KiB.
- No private keys, seed phrases, API keys or signed transaction payloads are
  returned.
- No backend signing, custody or transaction broadcast.
- No autonomous trading or market entry; entry-intent is unsigned only.
- No public operator creation/resolution/admin endpoints.
- No contract redeployment, new oracle, or accounting change.
- No paid AI calls from read endpoints; `allow_ai=False` is enforced.
- Funding status defaults to the persisted record; `?refresh=true` performs one
  bounded provider poll. A submitted deposit alone is never success.
- No frontend is implemented.
- The API is single-process/in-memory for rate limiting; a multi-instance
  deployment needs a shared limiter.
- The future market is open, but no funded position or market entry was made.
- Evidence and brief for the future market remain unavailable until its
  observation/resolution window.
- No auto-generated OpenAPI document; the authoritative contract is
  `docs/FRONTEND_INTEGRATION_CONTRACT.md`.

## 10. Deployment

Suggested production command:

```bash
WEB_API_HOST=0.0.0.0 WEB_API_PORT=8000 \
WEB_API_CORS_ORIGINS=https://notch.example \
python -m services.web_api
```

Put the process behind a TLS reverse proxy, keep the SQLite stores on persistent
storage, and never expose `NEAR_AI_KEY` or `TIDEPOOL_API_KEY` to the browser.
The API is read-only except for quote creation and unsigned entry-intent
preparation.

## 11. Remaining blockers

1. Frontend implementation and wallet signing UX.
2. No funded market entry or position has been made yet; entry-intent is
   preparation only.
3. The future market resolves after 2026-11-25; evidence/brief will become
   available then.
4. NEAR AI key/credits for live AI briefs (current briefs are fallback).
5. Multi-instance rate limiting and production observability are not implemented.
