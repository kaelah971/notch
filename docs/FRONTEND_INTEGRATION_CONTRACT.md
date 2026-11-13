# Notch frontend integration contract (S6)

Base URL (local): `http://127.0.0.1:8000`
Network: NEAR testnet only. Test assets have no value.

This contract is authoritative for the current stdlib HTTP API. The API does not
auto-generate OpenAPI; `docs/S6_WEB_API_VERIFICATION.md` and this document are the
schema.

## 1. Conventions

### Success envelope

```json
{
  "data": {},
  "meta": {}
}
```

`meta` is optional. List endpoints include `meta.count`.

### Error envelope

```json
{
  "error": {
    "code": "MARKET_NOT_FOUND",
    "message": "unknown market: ...",
    "details": {}
  }
}
```

`details` is optional. HTTP statuses:

| Status | Meaning |
| --- | --- |
| 200 | success |
| 400 | invalid input/body/amount |
| 404 | unknown market/trend/quote/endpoint |
| 409 | state conflict (closed market, insufficient collateral, paused entries) |
| 413 | body too large |
| 429 | rate limited |
| 500 | unexpected server error |
| 503 | NEAR RPC, provider, database, or AI catalog unavailable |

### Amounts

All token amounts are **strings in base units** and include `decimals`:

```json
{"balance": "101998769", "decimals": 6, "symbol": "USDC"}
```

Never convert settlement amounts to floating point. NEAR native amounts are
`yocto_near` strings with `decimals: 24`.

### Timestamps

- Contract market fields expose both raw nanoseconds (`open_at`, `close_at`,
  `resolve_after`) and UTC ISO strings (`open_at_utc`, `close_at_utc`,
  `resolve_after_utc`).
- `created_at`/`resolved_at` also include `_utc` ISO variants.
- Brief, trend, funding and health timestamps are UTC ISO-8601 strings.

### Market display status

| `display_status` | Meaning |
| --- | --- |
| `open_future` | Future-outcome market, entries open |
| `closed` | Closed, awaiting resolution |
| `resolved` | Resolved |
| `voided` | Voided |
| `historical_replay_open` | Historical replay, entries open (not a prediction) |
| `historical_replay_closed` | Historical replay, closed |
| `historical_replay_resolved` | Historical replay, resolved |

`is_historical_replay` is true for the two completed S2.5 demonstrations.
Historical replays must never be presented as active predictions.

### Brief status

- `AI_GENERATED`
- `NON_AI_FALLBACK`
- `INVALID_AI_FALLBACK`
- `AI_UNAVAILABLE_FALLBACK`

Ordinary read endpoints use `allow_ai=False`: they return a cached brief or a
deterministic source-only fallback. They never trigger a paid AI completion.

### Provider identifiers

- Brief `provider`: `near-ai` or `deterministic`.
- Brief `model`: configured NEAR AI model or `none`.
- Funding provider label: `tidepool-testnet`.
- No provider credential is returned.

### Draft proposals and empty states

`GET /api/markets` returns only onchain markets. Draft/future proposals are not
returned until an operator approves and broadcasts `create_market`. If no market
is open, the list still returns the actual markets (or `[]`) and entry-intent
returns 409 for closed/resolved markets. Never synthesize a market.

## 2. Routes

### `GET /api/health`

Returns API, RPC, contract, Radar DB, Oracle DB, brief-cache and funding
configuration health. No credentials.

```json
{
  "data": {
    "status": "ok",
    "network": "testnet",
    "checks": {
      "near_rpc": {"ok": true, "market_count": 2},
      "market_contract": {
        "ok": true,
        "collateral_token": "usdc.tidepool-sandbox.testnet",
        "min_entry_amount": "1000000"
      },
      "briefs": {"ok": true, "ai_key_present": false}
    }
  }
}
```

### `GET /api/trends`

Returns eligible S3A candidates, sorted by stored Radar score.

```json
{
  "data": [
    {
      "candidate_id": "cand_b279c92126deeecb4beb",
      "canonical_topic_id": "entity:nvidia",
      "title": "Nvidia",
      "category": "AI & Technology",
      "eligibility_status": "ELIGIBLE",
      "score": 85,
      "observed_at": "2026-11-12T00:21:10.784731Z",
      "source_count": 2,
      "sources": ["wikimedia", "hackernews"],
      "source_urls": ["https://en.wikipedia.org/wiki/Nvidia"],
      "settlement_coverage": {
        "window_start": "2026-11-04",
        "window_end": "2026-11-10",
        "latest_views": 123851,
        "latest_date": "2026-11-10"
      }
    }
  ],
  "meta": {"count": 11, "eligibility": "ELIGIBLE"}
}
```

### `GET /api/trends/{candidateId}`

Returns the candidate summary plus full `candidate` JSON and `evidence` array.

404 `TREND_NOT_FOUND` when absent.

### `GET /api/trends/{candidateId}/brief`

Returns a cached S5 brief or deterministic source-only fallback.

```json
{
  "data": {
    "brief_id": "brief_a86813abf29efd116c49",
    "brief_type": "radar",
    "topic": "Nvidia",
    "generation_status": "NON_AI_FALLBACK",
    "provider": "deterministic",
    "model": "none",
    "headline": "Nvidia: 123,851 Wikimedia views on 2026-11-10",
    "evidence_references": []
  },
  "meta": {"generation_mode": "cached_or_deterministic", "ai_call_triggered": false}
}
```

### `GET /api/markets`

Reads actual markets from `market.notch-dev.testnet` via `list_markets`.

```json
{
  "data": [
    {
      "market_id": "s3b-short-trend-nvidia-20261112T040029Z",
      "mode": "trend_trading",
      "status": "resolved",
      "display_status": "historical_replay_resolved",
      "is_historical_replay": true,
      "is_future_prediction": false,
      "winning_choice": "UP",
      "rule_hash": "sha256:79c8f464...",
      "evidence_hash": "sha256:583eac07...",
      "totals": ["1000000", "0"],
      "entries_open": false,
      "close_at_utc": "2026-11-12T05:30:29Z",
      "resolve_after_utc": "2026-11-12T05:35:29Z"
    }
  ],
  "meta": {"count": 3, "network": "testnet"}
}
```

If there are no markets, `data` is `[]` and `meta.count` is `0`. The API never
fabricates an open market.

### `GET /api/markets/{marketId}`

Returns the market summary plus:

- `onchain` raw contract view;
- `totals_view`;
- `contract_config`;
- `rule` canonical frozen rule when stored;
- `rule_record` hash/status/approval metadata;
- `evidence_digest`;
- `evidence_verified`.

404 `MARKET_NOT_FOUND` when absent.

### `GET /api/markets/{marketId}/evidence`

Returns canonical rule, evidence receipt, verification result and onchain hash
metadata. For an unresolved future market the rule is returned with
`evidence: null`, `evidence_available: false` and `verified: false`; 404 only
when no canonical rule exists. A brief requires evidence and returns 404
`EVIDENCE_NOT_AVAILABLE` until the observation/resolution window.

### `GET /api/markets/{marketId}/brief`

Returns `{brief, market}`. The brief includes a deterministic `resolution`
block derived from the frozen rule/evidence. The AI prose cannot change it.

### `GET /api/briefs/status`

Returns NEAR AI key presence, configured model, live catalog count and model
verification. It never returns the key.

```json
{
  "data": {
    "key_present": false,
    "configured_model": "z-ai/glm-5.3-flash",
    "model_verified": true,
    "catalog_count": 63
  }
}
```

## 3. Funding

### `GET /api/funding/tokens`

Live Tidepool testnet tokens and supported NEAR→USDC routes.

```json
{
  "data": {
    "tokens": [{"asset_id": "nep141:usdt.tidepool-sandbox.testnet", "symbol": "USDT", "decimals": 6}],
    "routes": [{"label": "USDT (near) -> USDC"}],
    "destination_asset": "nep141:usdc.tidepool-sandbox.testnet"
  }
}
```

### `POST /api/funding/quote`

Body:

```json
{
  "source_asset": "nep141:usdt.tidepool-sandbox.testnet",
  "amount": "1000000",
  "recipient": "notch-dev.testnet",
  "refund_to": "notch-dev.testnet",
  "deposit_type": "INTENTS",
  "slippage_bps": 100,
  "deadline_minutes": 30,
  "dry": true
}
```

- `dry: true` returns a price quote without a deposit address.
- `dry: false` creates a live quote and exact deposit instructions.
- The endpoint does not sign or transfer anything.
- Provider statuses, expiry and deposit instructions are preserved from S4.
- Unknown fields, invalid amounts/routes and unsupported deposit types return
  400.

### `GET /api/funding/status/{quoteId}`

Returns the persisted S4 quote, state, events and provider status. Add
`?refresh=true` for one bounded provider status poll. Success is never inferred
from a submitted deposit; S4 requires provider `SUCCESS` and a verified USDC
increase.

404 `QUOTE_NOT_FOUND` when absent.

### `GET /api/funding/readiness?account_id=...`

Returns actual NEP-141 USDC balance, storage registration and market-entry
readiness.

```json
{
  "data": {
    "account": "notch-dev.testnet",
    "balance": "101998769",
    "decimals": 6,
    "storage_registered": true,
    "min_market_entry": "1000000",
    "ready": true
  }
}
```

## 4. Wallets

### `GET /api/wallets/{accountId}/balances`

Returns NEAR native balance and USDC/USDT base-unit balances with decimals and
storage registration.

### `GET /api/wallets/{accountId}/positions`

Returns onchain positions only where `get_position` returns data. Each item
includes market status, stakes, total stake, claimed total, pending amount,
claimable and claim state, plus a deterministic market-level prediction result:
`prediction_status` is one of `PENDING`, `CORRECT`, `INCORRECT`, `VOIDED`, or
`UNKNOWN`; `prediction_choice` is populated only for a single-sided position;
`prediction_choices` preserves all selected sides; and finalized market
`evidence_hash`/`resolution_kind` are included when available.

Results are derived only from the finalized market view and the account's
aggregated position. Repeated entries on one side remain one market-level
prediction. A settled position with stakes on both sides is `UNKNOWN`, not an
automatic win or loss.

If the account has no positions, `data` is `[]`.

## 5. Entry preparation

### `POST /api/markets/{marketId}/entry-intent`

Body:

```json
{
  "account_id": "notch-dev.testnet",
  "side": 0,
  "stake": "1000000"
}
```

`side` may be an outcome index or a choice string (`"UP"`, `"Bitcoin"`, ...).

Validation:

- market exists;
- status is `open` and `entries_open` is true;
- close deadline is in the future;
- entries are not paused;
- collateral matches the configured Tidepool USDC;
- side is valid;
- stake is a positive integer at least `min_entry_amount`;
- wallet has registered storage and sufficient USDC.

Response:

```json
{
  "data": {
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
    "market_id": "...",
    "outcome": 0,
    "choice": "UP",
    "stake": "1000000",
    "collateral_token": "usdc.tidepool-sandbox.testnet",
    "min_entry_amount": "1000000",
    "signed": false,
    "broadcast": false
  },
  "meta": {"signed": false, "broadcast": false}
}
```

The backend never signs or broadcasts. The frontend must ask the wallet to sign
this exact transaction and submit it under user control. It must then call the
market contract views to confirm the position; the intent response is not proof
of a position.

Closed/resolved markets return 409 `MARKET_NOT_OPEN`. An open future market
returns 200 with an unsigned intent; the backend does not deposit or trade.

## 6. Frontend security requirements

- Never expose `NEAR_AI_KEY`, `TIDEPOOL_API_KEY`, private keys or seed phrases.
- Treat `NON_AI_FALLBACK` as non-AI text.
- Show historical replay markets with a clear historical label, never as active
  predictions.
- Show base-unit amounts with token decimals; do not do floating-point
  settlement arithmetic.
- Respect the API's 429 rate-limit response and 64 KiB request-body cap.
- Display deterministic resolution separately from AI prose.
- Do not treat a quote, deposit hash or `PENDING_DEPOSIT` as success.
- Do not create market positions from the API response; require a wallet-signed
  transaction and verify the onchain position.

## 7. Not implemented here

- Frontend UI.
- Operator market creation, resolution or admin endpoints.
- Custodial wallets or backend signing.
- Mainnet.
- New oracle or contract deployment.
- Paid AI calls from read endpoints.

The future-market proposal is documented separately in
`docs/S6_WEB_API_VERIFICATION.md`; it is not exposed as an onchain market until
the operator approves and broadcasts its creation transaction.
