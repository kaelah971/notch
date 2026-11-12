# S4 — NEAR Intents testnet funding

Date: 2026-11-12 (UTC)
Network: NEAR testnet only. Test tokens have no value.
Status: **S4.1 LIVE SWAP EXECUTED — PROVIDER SUCCESS — USDC BALANCE VERIFIED**

> **S4.1 execution (2026-11-12):** The operator approved the exact 2-USDT
> `ft_transfer_call`. Deposit tx `E4125h7BZDbubswjLr2mmM4BfVpxtVVGZ1Qmcq9beuq2`
> succeeded, Tidepool returned `SUCCESS`, and the wallet USDC balance increased
> from `100000000` to `101998769` base units. Settlement tx
> `2C9xGtKeMDfBvwdZwEAnkPAg2DRXGAPnggursmHWBY8N`. No market entry was submitted.
> The original 1-USDT quote is preserved as historical evidence. See section 14.

The approved S4.1 transfer was executed once. No additional chain transaction
was submitted after settlement. Market entry remains a separate approval and a
separate NEP-141 transaction.

## 1. Provider and boundary

| Field | Value |
| --- | --- |
| Provider | Tidepool 1Click-compatible testnet sandbox |
| Base URL | `https://www.usetidepool.tech` |
| Docs used | `/docs`, `/docs/quickstart`, `/docs/guides/first-swap`, `/docs/api-reference`, `/openapi.json` |
| Affiliation | Community-operated; not affiliated with NEAR, Defuse or 1Click |
| Official 1Click testnet | **No** — official 1Click is a mainnet service |
| Trust model | Single Tidepool maker; Tidepool derives custodial deposit-address keys |
| Mainnet assets | **Never used** |
| Confidentiality | Not supported by the sandbox; swaps settle publicly on testnet |
| Notch contract changes | None |
| Notch accounting changes | None |
| Frontend / S5 | Not implemented |

Tidepool is an **Intents-shaped testnet funding demonstration**, not a claim that
official NEAR Intents 1Click has a public testnet API. No real assets may be sent
to Tidepool addresses.

## 2. API client

Implemented in `services/intents/client.py`:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `get_tokens()` | `GET /v0/tokens` | Live asset discovery; optional `ondoTokens=1` |
| `quote(request)` | `POST /v0/quote` | Dry and live quotes |
| `submit_deposit(...)` | `POST /v0/deposit/submit` | Optional deposit-hash notification |
| `get_status(...)` | `GET /v0/status?depositAddress=...` | Provider status and swap details |

The client uses the documented 1Click request/response shapes and exact field
names. It has:

- request timeouts (15 s default);
- bounded retries for read-only GETs and deposit submission (2 by default);
- no automatic retry for quote creation, avoiding duplicate deposit addresses;
- a per-process minimum request interval;
- 429/`Retry-After` handling;
- typed parsing for tokens, quotes, statuses and swap details;
- error bodies with status/code/message but no request headers or API key;
- no signing, no private keys and no chain writes.

### Environment configuration

`.env.example` documents the adapter settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TIDEPOOL_BASE_URL` | `https://www.usetidepool.tech` | Provider base URL |
| `TIDEPOOL_API_KEY` | empty | Optional; any non-secret value selects the lower fee tier |
| `INTENTS_DATA_DIR` | `var/intents` | SQLite quote/event storage |
| `INTENTS_SOURCE_ASSET` | `nep141:usdt.tidepool-sandbox.testnet` | CLI default source asset |
| `NOTCH_ACCOUNT` | `notch-dev.testnet` | CLI default recipient |
| `NEAR_RPC_URL` | `https://rpc.testnet.near.org` | Balance/readiness RPC |
| `MARKET_CONTRACT` | `market.notch-dev.testnet` | Notch market contract reference |

No API key is required by Tidepool; the optional key is a fee-tier selector, not
an authentication secret.

## 3. Supported funding routes

Live `/v0/tokens` returned **31 tokens** on 2026-11-12. The destination is
required to be exactly:

```
nep141:usdc.tidepool-sandbox.testnet
```

The initial route family is **NEAR testnet source assets → NEAR test-USDC**.
The live token list currently exposes these NEAR sources:

| Source asset | Symbol | Decimals | Status |
| --- | --- | --- | --- |
| `nep141:usdt.tidepool-sandbox.testnet` | USDT | 6 | **Executable route; quote prepared** |
| `nep141:wnear.tidepool-sandbox.testnet` | wNEAR | 24 | Supported by validation/quote path |
| `nep141:wbtc.tidepool-sandbox.testnet` | wBTC | 8 | Supported by validation/quote path |
| `nep141:eth.tidepool-sandbox.testnet` | ETH | 18 | Supported by validation/quote path |
| `nep141:xaut.tidepool-sandbox.testnet` | XAUT | 6 | Supported by validation/quote path |

Tidepool also lists bridged USDC on Base Sepolia, Arbitrum Sepolia, Ethereum
Sepolia, BSC Testnet, Aurora Testnet, Solana devnet, Stellar testnet and Sui
testnet. **They are discovered but their deposit instructions are explicitly
marked unsupported** in this slice. The architecture keeps source-chain metadata
so a later slice can add them; Notch does not claim every chain is supported.

Destination chain/asset validation, source chain validation, decimals from live
metadata, integer base units, recipient/refund NEAR account validation, quote
expiry, slippage and a USD min/max policy are enforced before a quote is
accepted. The policy is **0.01–10.00 USD** per quote; source amounts remain
exact integer base units. No decimals or addresses are hard-coded from memory.

## 4. Funding state machine

```
IDLE
  -> QUOTED             dry quote
  -> AWAITING_DEPOSIT   live quote
       -> DEPOSIT_DETECTED   KNOWN_DEPOSIT_TX / INCOMPLETE_DEPOSIT
            -> PROCESSING    PROCESSING
                 -> SUCCESS  only after provider SUCCESS AND destination balance increase
                 -> REFUNDED provider refund
                 -> FAILED   provider failure or unverifiable success
       -> EXPIRED        deadline passed with no deposit
       -> FAILED
```

Provider status mapping:

| Provider status | Internal state |
| --- | --- |
| `PENDING_DEPOSIT` | `AWAITING_DEPOSIT` |
| `KNOWN_DEPOSIT_TX` | `DEPOSIT_DETECTED` |
| `INCOMPLETE_DEPOSIT` | `DEPOSIT_DETECTED` |
| `PROCESSING` | `PROCESSING` |
| `SUCCESS` | `SUCCESS` only if USDC balance increased; otherwise remains `PROCESSING` with an error |
| `REFUNDED` | `REFUNDED` |
| `FAILED` | `FAILED` |

A submitted deposit transaction alone never marks funding successful. The
service requires **both** a provider `SUCCESS` and a measured destination
USDC balance increase of at least `minAmountOut`. The pre-swap balance is
recorded at live-quote time. If it is missing, the service refuses to declare
success.

## 5. Real dry quote

Command:

```bash
python -m services.intents dry-quote \
  --source-asset nep141:usdt.tidepool-sandbox.testnet \
  --amount 1000000 \
  --recipient notch-dev.testnet \
  --deposit-type INTENTS \
  --deadline-minutes 60
```

Evidence: `docs/evidence/s4_dry_quote_usdt_usdc_20261112.json`

| Field | Value |
| --- | --- |
| Quote ID | `e8322ba0-a816-453d-a1bd-a6ea575c76dc` |
| Source | `nep141:usdt.tidepool-sandbox.testnet` (1 USDT) |
| Destination | `nep141:usdc.tidepool-sandbox.testnet` |
| Amount in | `1000000` base units |
| Estimated out | `999511` base units = `0.999511` USDC |
| Minimum out | `989515` base units = `0.989515` USDC |
| Implied fee | `0.0001` USD (1 bp stable-to-stable tier) |
| Expiry | `2026-11-12T08:06:24.735885Z` |
| Signature | `ed25519:3FWiQ64GfF6r6GVXcM17uR...` (full value in evidence JSON) |
| Deposit address | none (dry) |
| State | `QUOTED` |

## 6. Real live quote — prepared, not executed

Command:

```bash
TIDEPOOL_API_KEY=notch-s4-demo \
python -m services.intents prepare-swap \
  --source-asset nep141:usdt.tidepool-sandbox.testnet \
  --amount 1000000 \
  --recipient notch-dev.testnet \
  --deposit-type INTENTS \
  --deadline-minutes 60
```

Evidence: `docs/evidence/s4_live_quote_usdt_usdc_20261112.json`

| Field | Value |
| --- | --- |
| Quote ID | `c12aa519-9789-439e-aa4e-33732730b46b` |
| Source | `nep141:usdt.tidepool-sandbox.testnet` |
| Destination | `nep141:usdc.tidepool-sandbox.testnet` |
| Amount in | `1000000` base units (1 test USDT) |
| Estimated out | `999511` base units (0.999511 test USDC) |
| Minimum out | `989515` base units (0.989515 test USDC) |
| Implied fee | `0.0001` USD; no Notch fee |
| Deposit type | `INTENTS` |
| Provider deposit address | `e9fa20cc07cb1d7d5f01a7a1f81febae87ea1260601eb845c74513c7b4f8c204` |
| Deposit memo | none |
| Expiry | `2026-11-12T08:06:30.332Z` |
| Signature | `ed25519:549sTEUKrWEcrjas9S4DuE...` (full value in evidence JSON) |
| Provider status | `PENDING_DEPOSIT` |
| Local state | `AWAITING_DEPOSIT` |
| Deposit tx | **none** |
| Swap executed | **No** |

### Exact INTENTS deposit instruction

This is the transaction that would be signed **only after explicit approval**:

| Field | Value |
| --- | --- |
| Network | NEAR testnet |
| Signer | `notch-dev.testnet` |
| Receiver (outer transaction) | `usdt.tidepool-sandbox.testnet` |
| Method | `ft_transfer_call` |
| `receiver_id` | `verifier.tidepool-sandbox.testnet` |
| `amount` | `1000000` |
| `msg` | `e9fa20cc07cb1d7d5f01a7a1f81febae87ea1260601eb845c74513c7b4f8c204` |
| Attached deposit | `1` yoctoNEAR |
| Prepaid gas | `100 Tgas` |
| Storage registration | **Not required** for INTENTS |
| Expected output | `999511` base units USDC |
| Minimum output | `989515` base units USDC |
| Notch fee | `0` |

JSON args:

```json
{
  "receiver_id": "verifier.tidepool-sandbox.testnet",
  "amount": "1000000",
  "msg": "e9fa20cc07cb1d7d5f01a7a1f81febae87ea1260601eb845c74513c7b4f8c204"
}
```

### ORIGIN_CHAIN alternative (also prepared, not executed)

Evidence: `docs/evidence/s4_live_quote_origin_chain_20261112.json`

| Step | Contract | Method | Args | Attached | Gas |
| --- | --- | --- | --- | --- | --- |
| 1 | `usdt.tidepool-sandbox.testnet` | `storage_deposit` | `{"account_id":"ff4dab0d75dfd8529bc6700a327eece121758f0c6d4b686d91f2e1211775911b","registration_only":true}` | `0.00125 NEAR` | 30 Tgas |
| 2 | `usdt.tidepool-sandbox.testnet` | `ft_transfer` | `{"receiver_id":"ff4dab0d75dfd8529bc6700a327eece121758f0c6d4b686d91f2e1211775911b","amount":"1000000"}` | `1` yoctoNEAR | 30 Tgas |

The ORIGIN_CHAIN deposit address is the provider's fresh account; it is not
guessed. The storage price should be re-read before sending if this alternative
is selected.

## 7. Notch readiness

Evidence: `docs/evidence/s4_funding_readiness_20261112.json`

| Field | Value |
| --- | --- |
| Account | `notch-dev.testnet` |
| USDC asset | `nep141:usdc.tidepool-sandbox.testnet` |
| USDC balance | `100000000` base units (100 test USDC) |
| USDC storage | Registered |
| Market minimum | `1000000` base units |
| Ready for market entry | **Yes** |
| Source USDT balance | `100000000` base units (100 test USDT) |
| Source USDT storage | Registered |
| Source wNEAR/wBTC/ETH/XAUT | Present in the wallet; not used in this quote |
| Source balances evidence | `docs/evidence/s4_source_balances_20261112.json` |

This only reports readiness. **No market position is submitted by S4.** After a
confirmed swap, the frontend can use the existing NEP-141 `ft_transfer_call`
market-entry flow as a separate, user-approved transaction.

## 8. Security and failure handling

- **No signing / no broadcast** in the backend. The CLI stops at quote and
  deposit instructions.
- **Approval rule:** every chain transaction requires explicit approval for its
  signer, receiver, method, network, amount, fees and expected result. A general
  instruction to continue is not permission to send tokens.
- Quote expiry is enforced at quote validation, instruction generation and
  deposit recording.
- Integer base units only; float is used only for display/USD policy checks.
- Live token decimals and asset IDs are used; no hard-coded decimals.
- Source chain, source asset, destination asset, recipient and refund account
  are validated.
- Duplicate deposit protection uses a unique tx-hash index and rejects a second
  different tx for the same quote.
- Status polling is bounded (20 attempts by default; CLI override).
- Provider requests have timeouts, bounded retries and 429 handling.
- Quotes, statuses, deposit references and events are persisted in
  `var/intents/funding.sqlite3`.
- Refunds are recorded from provider `swapDetails`; no automatic refund action
  is attempted.
- Success requires provider `SUCCESS` **and** a verified USDC balance increase.
- No API key, seed phrase or private key is logged or stored.
- Quote signatures are preserved and shape-validated. Cryptographic verification
  is not implemented in the Python backend; the official
  `@defuse-protocol/one-click-sdk-typescript` helper should be used at the
  frontend/verification boundary if required. This does not replace the explicit
  transaction approval gate.

## 9. Automated tests

Command:

```bash
python -m unittest discover -s services/intents/tests -t .
```

Result: **47 tests passed**.

Coverage includes:

- live token discovery and route filtering;
- quote request validation (asset, chain, decimals, amount, USD min/max,
  slippage, recipient, refund, deadline);
- exact base-unit parsing/formatting;
- dry vs live quote validation, quote echo and expiry;
- unsupported routes and same-asset rejection;
- INTENTS and ORIGIN_CHAIN deposit instructions, verifier receiver, storage,
  gas, yoctoNEAR and memo;
- provider 400/429/timeout/invalid-JSON handling and bounded retries;
- funding state transitions;
- provider `SUCCESS` without balance increase remaining `PROCESSING`;
- balance verification, readiness and missing-storage cases;
- refunds, failures, expiry and duplicate deposits;
- idempotent quote/deposit processing.

No S1–S3 code was changed by this slice.

## 10. Testnet limitations

1. Tidepool is a community sandbox, not official NEAR Intents.
2. One maker fills quotes; no solver competition.
3. Deposit-address keys are custodial and derived by Tidepool.
4. Test tokens have no value; never send real assets.
5. Confidential Intents and private settlement are not available.
6. The official 1Click service is mainnet-only; this adapter does not assume a
   public official testnet API.
7. Bridged non-NEAR source chains are discovered but not yet given deposit
   instructions.
8. No paid provider, mainnet asset, contract redeployment, accounting change or
   frontend is used in this slice.
9. A live quote expires. If approval arrives after
   `2026-11-12T08:06:30.332Z`, request a new quote; do not deposit into an
   expired quote.
10. This slice demonstrates funding readiness only; it does not submit a market
    position and does not prove trading profit.

## 11. Frontend integration interface (not implemented)

Proposed backend routes, all server-side validated and rate-limited:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/funding/routes` | Live supported source routes to test USDC |
| `POST` | `/api/funding/quote` | Dry or live quote; returns quote, signature, expiry and deposit instructions |
| `GET` | `/api/funding/quotes/:quoteId` | Persisted quote, state and events |
| `POST` | `/api/funding/quotes/:quoteId/deposit` | Record a user-signed deposit tx hash; optional provider submit |
| `GET` | `/api/funding/quotes/:quoteId/status` | Provider status plus destination balance verification |
| `GET` | `/api/funding/readiness?account=...` | USDC balance/storage/market-entry readiness |

Frontend responsibilities:

1. Show the testnet-only warning and exact quote expiry.
2. Ask the wallet to sign the exact `ft_transfer_call` or ORIGIN_CHAIN steps.
3. Never ask the backend to hold keys or sign.
4. After deposit, submit the tx hash and poll status.
5. Show `SUCCESS` only when the backend confirms the balance increase.
6. Treat market entry as a separate, separately approved transaction.

## 12. Evidence files

- `docs/evidence/s4_tokens_20261112.json` — live `/v0/tokens` snapshot.
- `docs/evidence/s4_routes_20261112.json` — supported NEAR routes.
- `docs/evidence/s4_dry_quote_usdt_usdc_20261112.json` — real dry quote.
- `docs/evidence/s4_live_quote_usdt_usdc_20261112.json` — real live INTENTS quote and instructions.
- `docs/evidence/s4_live_quote_origin_chain_20261112.json` — real live ORIGIN_CHAIN quote and instructions.
- `docs/evidence/s4_status_pending_20261112.json` — provider `PENDING_DEPOSIT`.
- `docs/evidence/s4_deposit_args_intents.json` — exact INTENTS `ft_transfer_call` args.
- `docs/evidence/s4_deposit_storage_args_origin.json` — ORIGIN_CHAIN storage args.
- `docs/evidence/s4_deposit_transfer_args_origin.json` — ORIGIN_CHAIN transfer args.
- `docs/evidence/s4_funding_readiness_20261112.json` — wallet readiness.
- `docs/evidence/s4_source_balances_20261112.json` — live source-token balances/storage.
- `docs/evidence/s4_summary_20261112.json` — machine-readable summary.

S4.1 fresh 2-USDT evidence:

- `docs/evidence/s4_1_live_quote_usdt2_usdc_20261112.json` — fresh live quote and instructions.
- `docs/evidence/s4_1_status_pending_20261112.json` — provider `PENDING_DEPOSIT`.
- `docs/evidence/s4_1_funding_readiness_20261112.json` — wallet readiness.
- `docs/evidence/s4_1_provider_health_20261112.json` — compact provider health snapshot.
- `docs/evidence/s4_1_deposit_args_intents.json` — exact `ft_transfer_call` args.
- `docs/evidence/s4_1_summary_20261112.json` — machine-readable S4.1 summary.

No private key, seed phrase or signed transaction is stored in the repository.

## 13. S4.1 fresh 2-USDT live quote — pre-execution record (2026-11-12)

> This section preserves the quote and approval request exactly as prepared.
> The executed result is in section 14.

### Why a new quote

Notch market entry requires at least `1000000` USDC base units (1 test USDC).
The original S4 quote used 1 USDT and was not sufficient. A fresh 2-USDT quote
was created. **The old quote ID `c12aa519…` and old deposit address `e9fa…` are
not reused.**

### Chain and wallet state at quote time

Chain state checked at block `277332118` (`2026-11-12T07:29:46Z`):

| Item | Value |
| --- | --- |
| Signer/recipient | `notch-dev.testnet` |
| NEAR balance | `2985405063319137699999998` yoctoNEAR |
| USDT balance | `100000000` base units (100 test USDT) |
| USDC balance | `100000000` base units (100 test USDC) |
| USDT storage | Registered, total `1250000000000000000000` |
| USDC storage | Registered, total `1250000000000000000000` |
| Market contract | `market.notch-dev.testnet` |
| Market minimum entry | `1000000` base units |
| Market count | `2` (previous S2.5 markets) |

No token balance changed during quote preparation.

### Provider availability

`GET /v0/health` returned:

- RPC: `ok`
- Verifier: `ok` (`defuse` v0.4.5, code hash `a1afab98…`)
- Maker inventory: `ok`
- Prices: `ok: false`, source `fallback`, error `coingecko 429`

The quote API still returned a signed live quote using the provider's fallback
pricing. This is recorded, not hidden. The quote remains testnet-only and
valueless.

### Fresh live quote

Evidence: `docs/evidence/s4_1_live_quote_usdt2_usdc_20261112.json`

| Field | Value |
| --- | --- |
| Quote ID | `4787bc69-6a13-4ef6-853a-abfdaca6a0a6` |
| Source | `nep141:usdt.tidepool-sandbox.testnet` |
| Source amount | `2000000` base units = 2 test USDT |
| Destination | `nep141:usdc.tidepool-sandbox.testnet` |
| Estimated output | `1998953` base units = 1.998953 test USDC |
| Minimum output | `1978963` base units = 1.978963 test USDC |
| Minimum-output requirement | **PASS** — `1978963 >= 1000000` |
| Implied fee | `0.0002` USD; no Notch fee |
| Slippage | `100` bps |
| Deposit type | `INTENTS` |
| Provider deposit address | `c4990383f59eb49521cbe155bfc0f9cf567aff9411d72e127199df0bee72e6e9` |
| Deposit memo | none |
| Recipient | `notch-dev.testnet` |
| Refund destination | `notch-dev.testnet` |
| Expiry | `2026-11-12T08:30:41.527Z` |
| Provider signature | `ed25519:55FYfaW2i82ZoQwLTyQLdWqYwc3KMqxt8znmeKMm9ZnKrLvFj9pjxGERSbEgy6zRNscGrXY4JrNymqBbPfwBwLcU` |
| Provider status | `PENDING_DEPOSIT` |
| Local state | `AWAITING_DEPOSIT` |
| Deposit transaction | **none** |
| Swap executed | **No** |

The quote signature is returned and shape-validated. Cryptographic verification
with the official TypeScript SDK is still a production-hardening item.

### Exact transaction — historical approval request

| Field | Value |
| --- | --- |
| Network | NEAR testnet |
| Signer | `notch-dev.testnet` |
| Token contract / outer receiver | `usdt.tidepool-sandbox.testnet` |
| Method | `ft_transfer_call` |
| NEP-141 `receiver_id` | `verifier.tidepool-sandbox.testnet` |
| `amount` | `2000000` |
| `msg` | `c4990383f59eb49521cbe155bfc0f9cf567aff9411d72e127199df0bee72e6e9` |
| Attached deposit | `1` yoctoNEAR |
| Prepaid gas | `100 Tgas` |
| Storage registration | Not required for INTENTS |
| Expected output | `1998953` base units USDC |
| Minimum output | `1978963` base units USDC |
| Refund destination | `notch-dev.testnet` |
| Fees | `0.0002` USD provider fee; Notch fee `0` |
| Quote expiry | `2026-11-12T08:30:41.527Z` |

Exact args: `docs/evidence/s4_1_deposit_args_intents.json`

```json
{
  "amount": "2000000",
  "msg": "c4990383f59eb49521cbe155bfc0f9cf567aff9411d72e127199df0bee72e6e9",
  "receiver_id": "verifier.tidepool-sandbox.testnet"
}
```

**No transaction has been signed or broadcast.** Approval is required for this
specific transaction. If the quote expires before approval, regenerate and
request fresh approval; do not reuse this quote or approval.

### Execution after approval (completed)

1. Re-read chain time and confirm the quote has not expired.
2. Sign and broadcast exactly the `ft_transfer_call` above from
   `notch-dev.testnet`.
3. Record the deposit transaction hash.
4. Optionally call `POST /v0/deposit/submit` with the hash and exact deposit
   address.
5. Poll `GET /v0/status` with bounded attempts.
6. Do **not** treat `PENDING_DEPOSIT` or `PROCESSING` as success.
7. Require provider `SUCCESS`.
8. Independently read the USDC balance and require an increase of at least
   `1978963` base units.
9. Report `REFUNDED`/`FAILED` accurately if either occurs.
10. Check readiness for a Notch market entry; do **not** enter a market without a
    separate approval and a separate NEP-141 transaction.

### S4.1 evidence

- `docs/evidence/s4_1_live_quote_usdt2_usdc_20261112.json`
- `docs/evidence/s4_1_status_pending_20261112.json`
- `docs/evidence/s4_1_status_final_20261112.json`
- `docs/evidence/s4_1_funding_readiness_20261112.json`
- `docs/evidence/s4_1_funding_readiness_after_20261112.json`
- `docs/evidence/s4_1_provider_health_20261112.json`
- `docs/evidence/s4_1_deposit_args_intents.json`
- `docs/evidence/s4_1_deposit_record_20261112.json`
- `docs/evidence/s4_1_balances_after_20261112.json`
- `docs/evidence/s4_1_execution_20261112.json`
- `docs/evidence/s4_1_summary_20261112.json`

### S4.1 verification

- S4 tests: **47 passed** (`python -m unittest discover -s services/intents/tests -t .`).
- No contract redeployment.
- No accounting change.
- No frontend.
- No mainnet funds.
- No automatic market entry.
- No private key or transaction signature exposed.

## 14. S4.1 execution evidence (2026-11-12)

### Approval

The operator explicitly approved the exact 2-USDT `ft_transfer_call` for quote
`4787bc69-6a13-4ef6-853a-abfdaca6a0a6`. The approval was for that specific
transaction, signer, token contract, amount and deposit address.

### Preflight

Before broadcasting:

- Chain time: `2026-11-12T08:10:28Z`
- Quote expiry: `2026-11-12T08:30:41.527Z`
- Quote was still valid.
- Source: `nep141:usdt.tidepool-sandbox.testnet`
- Amount: `2000000`
- Destination: `nep141:usdc.tidepool-sandbox.testnet`
- Deposit type: `INTENTS`
- Deposit address: `c4990383f59eb49521cbe155bfc0f9cf567aff9411d72e127199df0bee72e6e9`
- Deposit memo: none
- Recipient/refund: `notch-dev.testnet`
- Minimum output: `1978963` — above `1000000`
- Wallet USDT: `100000000`; USDC: `100000000`
- USDT storage: registered
- Provider status: `PENDING_DEPOSIT`
- No prior deposit tx

All preflight checks matched the approved transaction.

### Deposit transaction

| Field | Value |
| --- | --- |
| Hash | `E4125h7BZDbubswjLr2mmM4BfVpxtVVGZ1Qmcq9beuq2` |
| Explorer | <https://testnet.nearblocks.io/txns/E4125h7BZDbubswjLr2mmM4BfVpxtVVGZ1Qmcq9beuq2> |
| Signer | `notch-dev.testnet` |
| Token contract | `usdt.tidepool-sandbox.testnet` |
| Method | `ft_transfer_call` |
| NEP-141 receiver | `verifier.tidepool-sandbox.testnet` |
| Amount | `2000000` |
| Attached deposit | `1` yoctoNEAR |
| Gas | `100 Tgas` |
| Result | **SUCCESS** |

Events confirmed:

- NEP-141 `ft_transfer`: `notch-dev.testnet` → `verifier.tidepool-sandbox.testnet`, `2000000`
- NEP-245 `mt_mint`: `2000000` to the quote's Intents deposit account `c499…`

`POST /v0/deposit/submit` was called with the deposit hash and exact deposit
address.

### Provider settlement

| Field | Value |
| --- | --- |
| Provider status | **`SUCCESS`** |
| Updated at | `2026-11-12T08:11:57.335Z` |
| Settlement tx | `2C9xGtKeMDfBvwdZwEAnkPAg2DRXGAPnggursmHWBY8N` |
| Settlement explorer | <https://testnet.nearblocks.io/txns/2C9xGtKeMDfBvwdZwEAnkPAg2DRXGAPnggursmHWBY8N> |
| Intent hashes | `HPs9bDPppWYYHS1TJqPiHAyEgn2upgvoY13UMHCNP2Vi`, `FTMxkQTsqvMgX8FZPEBUcJm2To43zRo95QdZsr9yzyaJ` |
| Actual amount out | `1998769` base units |
| Actual amount out formatted | `1.998769` USDC |
| Withdraw fee | `0` |
| Refund | None — provider `SUCCESS`, not `REFUNDED`/`FAILED` |

### Balances and actual receipt

| Point | USDC | USDT |
| --- | --- | --- |
| Before | `100000000` | `100000000` |
| After | `101998769` | `98000000` |
| Delta | **`+1998769`** | `-2000000` |

- Quote estimated output: `1998953` base units.
- Quote minimum output: `1978963` base units.
- Actual received: **`1998769` base units = 1.998769 test USDC**.
- Actual was 184 base units below the quote estimate but **above the minimum**.
- Independent `ft_balance_of` check confirmed the increase.
- USDC storage remains registered.
- NEAR balance after execution: `2984597446695632999999997` yoctoNEAR.

### Funding readiness

| Field | Value |
| --- | --- |
| USDC balance | `101998769` base units |
| Market minimum | `1000000` base units |
| Storage | Registered |
| Ready for a Notch market entry | **Yes** |
| Market entry submitted | **No** |
| Market count | `2` (unchanged S2.5 markets) |

The received collateral is sufficient for a 1-USDC market entry, but **no market
entry was submitted**. That remains a separate approval and a separate NEP-141
transaction.

### Tests

```bash
python -m unittest discover -s services/intents/tests -t .
```

**47 tests passed.** No S1–S3 tests were rerun; no existing code was changed.

### Constraints preserved

- No contract redeployment.
- No accounting change.
- No frontend.
- No S5.
- No mainnet funds.
- No automatic market entry.
- No private key or transaction signature stored in the repository.
- One approved chain transaction was broadcast; no additional chain transaction
  was submitted after settlement.

### Evidence files

- `docs/evidence/s4_1_execution_20261112.json`
- `docs/evidence/s4_1_deposit_record_20261112.json`
- `docs/evidence/s4_1_status_final_20261112.json`
- `docs/evidence/s4_1_balances_after_20261112.json`
- `docs/evidence/s4_1_funding_readiness_after_20261112.json`
- `docs/evidence/s4_1_summary_20261112.json`
- `docs/evidence/s4_1_status_pending_20261112.json` (pre-deposit)
- `docs/evidence/s4_1_live_quote_usdt2_usdc_20261112.json`
- `docs/evidence/s4_1_deposit_args_intents.json`

### Remaining integration gaps

1. Market entry is intentionally separate and not submitted.
2. Quote signature is shape-validated; cryptographic verification via the
   official TypeScript SDK remains production hardening.
3. No frontend/S5 consumer surface.
