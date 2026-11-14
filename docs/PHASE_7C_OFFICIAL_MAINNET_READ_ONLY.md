# Phase 7C — Official NEAR Intents 1Click Mainnet Read-Only V1

Status: implemented, read-only, not production execution-ready.

Phase 7C adds official NEAR Intents 1Click Mainnet discovery and dry quoting while preserving the existing Tidepool Testnet funding flow. It does **not** fund the deployed Notch market, which remains NEAR Testnet-only.

## Scope and safety boundary

- Official provider: `https://1click.chaindefuser.com`
- Live metadata: `GET /v0/tokens`
- Dry quotes: `POST /v0/quote` with `dry: true`
- Official quote signature key: `ed25519:reYaWhvwu8Jzo3WUM3zhn6VrhuMEF4eADL17qtRVifc`
- Unauthenticated non-`ANY_INPUT` quotes carry the provider-documented additional 25 bps fee.
- Mainnet assets are filtered from the live catalog and are never mapped to Tidepool Testnet identifiers.
- The official adapter cannot submit deposits, query execution status, create wet quotes, sign, broadcast, deploy, settle, or automatically activate a route.
- The existing Tidepool endpoints and Testnet destination remain unchanged.

The UI labels the official surface `READ-ONLY / FUTURE`. Every quote response is marked dry, exposes no deposit address, and returns `signed: false`, `broadcast: false`, and `execution_supported: false` metadata.

## Configuration

Server-side variables are documented in [`.env.example`](../.env.example):

```text
NEAR_INTENTS_BASE_URL=https://1click.chaindefuser.com
NEAR_INTENTS_API_KEY=
NEAR_INTENTS_DESTINATION_ASSET=nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1
NEAR_INTENTS_RECIPIENT=
NEAR_INTENTS_REFUND_TO=
```

The destination identifier is an observed official Mainnet catalog asset and is revalidated against the live token response. It is not a Testnet-to-Mainnet conversion rule. A partner JWT, when available, is sent only as a server-side `Authorization: Bearer` header and is never returned to the browser.

`NEAR_INTENTS_RECIPIENT` and `NEAR_INTENTS_REFUND_TO` are optional defaults. A dry quote request must still provide a valid Mainnet recipient and source-chain refund address. The connected Testnet account is never reused as a Mainnet recipient.

## API

### Mainnet discovery

```http
GET /api/funding/mainnet/tokens
```

The response includes:

- provider and `network: Mainnet` identity;
- live token metadata, source tokens, NEAR destination candidates, routes, and source chains;
- `quote_mode: dry_only` or `unavailable`;
- authentication mode and fee notice without credential material;
- explicit execution blockers and `execution_supported: false`.

### Mainnet dry quote

```http
POST /api/funding/mainnet/quote
Content-Type: application/json
```

Required request fields:

```json
{
  "source_asset": "<exact assetId from live /v0/tokens>",
  "destination_asset": "<exact configured Mainnet NEAR asset>",
  "source_chain": "base",
  "amount": "1000000",
  "recipient": "verified-account.near",
  "refund_to": "<source-chain address>",
  "deposit_type": "ORIGIN_CHAIN",
  "slippage_bps": 100,
  "deadline_minutes": 15,
  "dry": true
}
```

Unknown execution or confirmation fields are rejected. `dry: false` is rejected with `OFFICIAL_MAINNET_DRY_ONLY`. The response is validated for exact request identity, route identity, deadline, amount bounds, Mainnet account separation, and the official Ed25519 signature.

## Validation and separation

The official adapter fails closed when:

- the base URL is not the official HTTPS host;
- a configured destination, market, collateral, or recipient is a Testnet identifier;
- a source or destination asset is absent from the live Mainnet catalog;
- a route contains a `.testnet` asset;
- the recipient is a `.testnet` account;
- a source-chain refund address is invalid;
- a quote response is unsigned, mismatched, expired, or otherwise malformed;
- an execution/status operation is attempted.

Tidepool Testnet continues to enforce its own Testnet destination and chain-specific refund validation. The two adapters have separate provider IDs, endpoints, configuration, UI labels, and validation paths.

## Genuine live observation

During Phase 7C implementation, official discovery returned 231 live token records, including a live Base USDC source and NEAR USDC destination. A genuine dry quote was requested for 1,000,000 source units:

- estimated output: `995596`;
- minimum output: `985640`;
- refund fee: `2400`;
- withdraw fee: `4202`;
- provider time estimate: 35 seconds;
- official signature verification: `true`;
- deposit address: none;
- no source transaction was authorized or submitted.

Evidence is recorded in [`docs/evidence/phase7c_official_mainnet_dry_quote_20261114.json`](evidence/phase7c_official_mainnet_dry_quote_20261114.json). Provider quotes are volatile; these values are evidence of an observed response, not a guaranteed price or execution offer.

## Production prerequisites before any execution work

Phase 7C is not a production funding approval. Before a separate execution phase:

1. deploy the API behind public HTTPS with persistent storage and production CORS;
2. obtain and rotate an official partner JWT through an approved secret manager;
3. independently verify the Mainnet destination asset, recipient policy, refund policy, and fee economics;
4. define a separate Mainnet market/collateral contract and verify its code, configuration, finality, and reconciliation rules;
5. design least-privilege wallet authorization and signer isolation; Notch must not receive exportable keys;
6. add replay protection, idempotency, status/finality monitoring, refund handling, emergency stop, alerts, and immutable audit records;
7. obtain explicit human approval for any future wet quote or source-chain transaction;
8. run a bounded Testnet/Mainnet separation review and deployed-origin smoke test.

Until all prerequisites are independently approved, the only supported action is read-only catalog inspection and a dry quote.

## Verification

Focused Phase 7C checks:

```text
python -m unittest services.intents.tests.test_phase7c -v
python -m unittest services.web_api.tests.test_phase7c_api -v
cd web && node --test tests/funding.test.mjs
cd web && npm run build
```

The build may retain the repository's existing chunk-size, browser-externalization, and dependency `eval` warnings. These are unrelated to Mainnet execution; no automatic transaction path was added.
