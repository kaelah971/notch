# Phase 7B — Real Testnet Cross-Chain Funding V1

Status: implemented as a user-authorized, manual-deposit Base Sepolia vertical slice. No source-chain transaction was signed, broadcast, or submitted during implementation.

## Enabled route

The first live route is selected dynamically from Tidepool `/v0/tokens` and is enabled only when the live catalog contains:

- source chain: **Base Sepolia**, chain ID `84532`;
- source asset: the live Base USDC asset ID and ERC-20 contract returned by Tidepool;
- destination chain: **NEAR Testnet**;
- destination asset: `nep141:usdc.tidepool-sandbox.testnet`;
- recipient: the connected, user-controlled NEAR Testnet account;
- deposit type: `ORIGIN_CHAIN`;
- recipient type: `DESTINATION_CHAIN`;
- refund type: `ORIGIN_CHAIN`.

The source contract and decimals are never guessed or hardcoded by the UI. The server validates the selected asset against the current provider catalog and requires the selected source chain to be `base` for the Phase 7B live endpoint.

## Live quote boundary

Phase 7A `POST /api/funding/quote` remains dry-only. `dry=false` still returns `WET_QUOTES_DISABLED`.

Phase 7B adds `POST /api/funding/live-quote`. It requires all of:

- `dry: false`;
- `confirm_live_quote: true`;
- `confirm_testnet: true`;
- `source_chain: base`;
- explicit source asset, amount, recipient and refund address.

The service verifies the Tidepool maker signature against:

`ed25519:U1Mu4u1nHnHmgABpCkfDGXt2FZj8k29UGqhkMAu4iWY`

It also validates the echoed request, exact amount, destination, recipient, refund details, deadline, minimum output, deposit address and provider metadata. The live response creates a single-use provider deposit address, but it does not transfer funds.

## Deposit authorization

The first vertical slice deliberately uses a manual Base Sepolia deposit rather than an injected EVM wallet adapter. Notch never receives a seed phrase, private key or allowance and never initiates a transfer.

The UI shows:

- Base Sepolia chain ID and exact token contract;
- exact quoted base-unit amount;
- provider deposit address and memo, if returned;
- NEAR destination and refund address;
- minimum output and deadline;
- provider signature state;
- Tidepool testnet/community-operated warning.

The user must use an external wallet they control, approve exactly one ERC-20 transfer, then paste the resulting `0x` transaction hash. `POST /api/funding/deposit` requires `user_confirmed: true` and submits only that user-provided reference to Tidepool's `POST /v0/deposit/submit`.

## Status and recovery

`GET /api/funding/status/{quote_id}?refresh=true` performs one bounded provider poll. The browser persists only the quote reference, quote metadata and user-submitted transaction hash in local storage, so refresh/resume does not create a second deposit.

Supported provider states:

- `PENDING_DEPOSIT`;
- `KNOWN_DEPOSIT_TX`;
- `INCOMPLETE_DEPOSIT`;
- `PROCESSING`;
- `SUCCESS`;
- `REFUNDED`;
- `FAILED`.

Only `SUCCESS`, `REFUNDED`, `FAILED` and the local expired state are terminal in the Notch UI. Partial, delayed and unknown states remain actionable.

Duplicate transaction references are rejected across quotes and are idempotent for the same quote. Quote expiry, wrong-network hashes, mismatched status quote metadata, provider errors and missing memos remain visible without claiming funding.

## Destination verification

Provider `SUCCESS` is not displayed as funded by itself. Notch independently:

1. checks that the status quote still matches the stored source asset, destination asset, recipient, amount and deposit address;
2. reads `ft_balance_of` for `usdc.tidepool-sandbox.testnet` on the requested NEAR account;
3. compares the post-success balance against the pre-quote balance and requires a positive delta at least equal to `minAmountOut`;
4. exposes provider settlement hashes and NEAR transaction references when Tidepool returns them.

The UI distinguishes:

- `PROVIDER_SUCCESS` — Tidepool reports success;
- `DESTINATION_VERIFICATION_PENDING` — provider success exists but the independent balance check is not complete;
- `DESTINATION_VERIFIED` — the requested NEP-141 balance increase passed.

Only `DESTINATION_VERIFIED` is presented as funded and ready to refresh the existing Notch collateral/market-entry flow.

## Explicit approval still required

This implementation did not send a testnet transaction. Before the first real deposit, the user must explicitly approve one small Base Sepolia USDC transfer after reviewing a freshly generated live quote. The user must verify the chain ID, token contract, exact amount, provider deposit address, memo, NEAR recipient, refund address and deadline in their external wallet.

A complete transfer proof will require the source transaction hash, Tidepool correlation ID and terminal status, provider settlement evidence, destination NEAR transaction/NEP-141 evidence and an independently observed balance increase. Until those artifacts exist, the milestone is **implemented / live-quote-ready**, not transfer-complete.
