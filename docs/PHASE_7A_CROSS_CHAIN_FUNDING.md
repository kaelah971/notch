# Phase 7A — Cross-Chain Funding Discovery V1

Status: implemented as read-only, dry-quote discovery. No deposit address, transfer, signing, broadcast, swap execution or market-entry transaction is available from this slice.

## Network boundary

Notch prediction markets remain on **NEAR Testnet** and use:

- destination asset: `nep141:usdc.tidepool-sandbox.testnet`;
- destination chain: `near` / NEAR Testnet;
- market collateral contract: `usdc.tidepool-sandbox.testnet`.

The funding provider is **Tidepool**, an independent community-operated 1Click-compatible **Testnet sandbox** at `https://www.usetidepool.tech`. The configuration rejects other provider hosts, including a Mainnet 1Click host, and rejects non-`.testnet` destination collateral. Mainnet and Tidepool Testnet assets are never mixed.

Tidepool's documented test bridges expose external testnets such as Base Sepolia, Arbitrum Sepolia, Ethereum Sepolia, BSC Testnet, Aurora Testnet, Solana devnet, Stellar testnet, Sui testnet, XRP Ledger testnet, Bitcoin testnet4 and Hypercore testnet. The UI discovers this list from the live provider response rather than hardcoding routes.

## User journey

Portfolio → Get test-USDC:

1. choose a source testnet;
2. choose a live-discovered token and preserve its exact asset ID and decimals;
3. enter an exact decimal amount;
4. enter a user-controlled refund address for that source chain;
5. inspect a genuine `POST /v0/quote` request with `dry: true`;
6. review the route, recipient, output, minimum output, quote freshness, provider fee fields and provider attribution;
7. return to Notch's open prediction markets.

A dry quote is explicitly labelled as not funded. No deposit address is accepted from a dry response, and the web API rejects `dry: false` with `WET_QUOTES_DISABLED`.

## Provider/API paths

Server-side provider calls:

- `GET https://www.usetidepool.tech/v0/tokens`
- `POST https://www.usetidepool.tech/v0/quote` with `dry: true`

Notch API paths:

- `GET /api/funding/tokens`
- `POST /api/funding/quote`

The browser never receives provider configuration or API keys. Provider errors are returned as bounded, human-readable API errors; raw provider bodies are not exposed in public quote payloads. Requests retain bounded timeout, retry and rate-limit behavior from the existing Tidepool client.

## Dynamic asset and amount handling

`/api/funding/tokens` returns live token metadata, including:

- exact `asset_id`;
- exact `decimals`;
- blockchain and symbol;
- destination asset and chain;
- externally offered source chains;
- provider/network attribution;
- latest provider token observation timestamp.

The frontend converts user decimal input to integer base units with `BigInt`-based `parseUnits`. Decision-critical amounts are rendered from `amountIn`, `amountOut` and `minAmountOut`, never from USD estimates.

Server validation rejects unsupported assets, wrong source-chain claims, wrong destination assets, incorrect recipient networks, invalid amounts, expired/far deadlines, invalid slippage, and refund addresses that do not match the selected source chain. Supported refund address shapes include EVM, Solana, Stellar, Sui, XRP, Bitcoin and NEAR testnet formats as applicable.

## Genuine read-only quote evidence

A live dry quote was requested from Tidepool during Phase 7A verification:

- provider: Tidepool Testnet sandbox;
- source chain: Base Sepolia (`base`);
- source asset: `nep141:base-0x38d81431b9f76d9699af7517040d5221d9dea252.tp-omft.testnet`;
- source decimals: `6`;
- destination chain: NEAR Testnet (`near`);
- destination asset: `nep141:usdc.tidepool-sandbox.testnet`;
- destination decimals: `6`;
- amount: `1000000` base units = `1` source USDC;
- estimated output: `997400` base units = `0.9974` test-USDC;
- minimum output: `987426` base units = `0.987426` test-USDC;
- provider time estimate: `60` seconds;
- quote timestamp: `2026-11-14T03:01:01.208Z`;
- provider deadline: `2026-11-14T03:31:00.715Z`;
- recipient: `notch-dev.testnet`;
- refund type: `ORIGIN_CHAIN` with a supplied Base-format test address;
- provider correlation ID: `54883d06-38e4-4e1c-ab9c-3feac5fc1e51`;
- response was accepted only because it was `dry: true` and contained no deposit address.

The USD values returned by the provider are display estimates only. The UI does not use them to calculate output or minimum output.

## Changed files

- `services/intents/config.py` — strict Tidepool Testnet provider/destination safeguards.
- `services/intents/models.py` — public quote serialization no longer exposes raw provider bodies; private storage retains them for the existing Phase 7B state machine.
- `services/intents/validation.py` — external route selection and chain-specific refund validation.
- `services/intents/service.py` — optional external source-chain routing and dynamic external route discovery.
- `services/intents/cli.py` — external route discovery and source-chain-aware dry-quote arguments; existing wet state-machine commands remain outside the Phase 7A web boundary.
- `services/intents/store.py` — private record serialization for existing quote state.
- `services/web_api/app.py` — dynamic token metadata, external routes, dry-only quote boundary and provider metadata.
- `services/web_api/tests/test_api.py` — quote-only API boundary coverage.
- `services/intents/tests/test_phase7a.py` — external asset/decimal, route, network and refund validation.
- `web/src/api/client.ts` and `web/src/api/types.ts` — funding discovery and provider quote types.
- `web/src/pages/Funding.tsx` — read-only Funding Wallet discovery flow.
- `web/src/pages/Portfolio.tsx` and `web/src/pages/Portfolio.css` — wallet-balance surface integration and responsive layout.
- `web/package.json` — `npm run test:funding`.
- `web/tests/funding.test.mjs` — frontend quote-only and exact-unit regression coverage.

## Phase 7B handoff — deliberately not implemented

A complete testnet swap still requires a separate, explicitly approved milestone for:

- user-approved quote commitment;
- unique deposit address and optional memo;
- deadline/expiration handling and quote refresh;
- external wallet authorization;
- deposit transaction reference and provider submission;
- status polling and recovery;
- `SUCCESS`, `REFUNDED`, `FAILED` and `INCOMPLETE_DEPOSIT` handling;
- independent destination balance verification;
- clear return to Notch's prediction-entry flow after verified collateral arrival.

No Phase 7B state-changing operation is initiated by the Phase 7A UI or `/api/funding/quote`.

## Limitations

- Tidepool liquidity, supported assets and token prices are provider-controlled and can change; the UI shows an unavailable state rather than inventing a route.
- A valid dry quote does not prove that a future live quote, deposit address or route will remain available.
- External wallet connection is not part of Phase 7A; refund address entry is user-controlled text validated for the selected chain.
- Test tokens have no monetary value and source-chain gas would be required for a future deposit.
- Existing lower-level Phase 7B service/state code remains for the handoff, but it is not reachable through the Phase 7A web API or UI.
