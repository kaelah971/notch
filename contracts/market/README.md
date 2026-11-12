# Notch market contract — S2 interface and operations

`notch-market` is the shared settlement engine for Notch's binary attention
markets. **S2 enables both modes on one contract:**

- **Trend Trading** — first choice (UP) vs second choice (DOWN) against a
  predefined target.
- **Trend Battle** — Topic A vs Topic B under one frozen comparison rule.

Both modes reuse the same `ft_on_transfer`, escrow accounting, position
storage, pooled payout formula, void refunds, callback-confirmed claims and
failed-transfer recovery. The only mode-specific code is creation validation
and the resolver-only tie path.

- Rust: 1.96.0
- `near-sdk`: 5.30.1
- Target: `wasm32-unknown-unknown`
- Artifact: [`res/notch_market.wasm`](res/notch_market.wasm)
  (`sha256:9892eaa0c113378ca188137d6565d444ff6a8794bda3a596ce1fdcbb692f0f08`,
  451,574 bytes)
- Network: **NEAR testnet only**
- Fees: **0**

## 1. Security and accounting invariants

1. Only the NEP-141 token configured at initialization can fund a market.
2. `escrow_total = Σ position stakes` for every market at all times.
3. `escrow_total = paid_total + pending_total + unclaimed_reserve` for every
   market. `unclaimed_reserve` contains unclaimed stakes and rounding dust.
4. A payout is never marked paid until the token's `ft_transfer` callback
   reports success.
5. A final state is immutable. A resolved market cannot be voided, a voided
   market cannot be resolved, and a tie-voided battle cannot be turned into a
   winner.
6. No admin method transfers tokens. Escrow only leaves through `claim` /
   `claim_refund` for the recorded entitlement.
7. Fees are zero and positions are fully collateralized.
8. Trend Trading and Trend Battles share the same accounting implementation;
   there is no second payout engine.

## 2. Roles and initialization

`new(owner, operator, resolver, collateral_token, min_entry_amount)` is a
one-time `#[init]` method with an additional state-exists guard. Minimum entry
must be > 0.

| Role | Capabilities |
| --- | --- |
| `owner` | Rotate operator/resolver, pause entries, void markets |
| `operator` | Create markets, pause entries |
| `resolver` | Resolve winners, settle battle ties, void markets |
| Any participant | Claim a payout or void refund |
| Anyone | Close a market after its deadline (time-guarded, idempotent) |

Changing operator or resolver does not alter existing markets. The collateral
token cannot be changed. The global entry pause blocks new markets and entries;
claims and refunds remain available.

## 3. Timestamps

All timestamps are **nanoseconds since the Unix epoch**, using
`env::block_timestamp()`. JSON inputs and views encode them as strings (`U64`).

Entries are accepted for `open_at <= block_timestamp < close_at`. At exactly
`close_at` an entry is rejected. Creation requires `open_at < close_at <=
resolve_after` and `close_at > now`.

## 4. Market configuration

`create_market` takes one named argument `args`.

### 4.1 Trend Trading

```json
{
  "args": {
    "market_id": "wb-ai-agents-15pct",
    "mode": "trend_trading",
    "question": "Will daily article views for Topic X grow by at least 15%?",
    "choices": ["UP", "DOWN"],
    "source_id": "wikimedia-pageviews-v1",
    "rule_hash": "sha256:<64 hex chars>",
    "open_at": "1760000000000000000",
    "close_at": "1760003600000000000",
    "resolve_after": "1760003600000000000",
    "invalidation_policy": "refund_on_void"
  }
}
```

`battle` is optional and must be absent/null for Trend Trading. It is omitted
above; `#[serde(default)]` keeps S1-style payloads valid.

### 4.2 Trend Battle

```json
{
  "args": {
    "market_id": "battle-ai-vs-gaming",
    "mode": "trend_battle",
    "question": "Which topic grows faster: AI Agents or Gaming?",
    "choices": ["AI Agents", "Gaming"],
    "source_id": "wikimedia-pageviews-v1",
    "rule_hash": "sha256:<64 hex chars>",
    "open_at": "1760000000000000000",
    "close_at": "1760003600000000000",
    "resolve_after": "1760003600000000000",
    "invalidation_policy": "refund_on_void",
    "battle": {
      "topic_a": {
        "topic_id": "ai-agents",
        "source_id": "wikimedia-pageviews-v1",
        "project": "en.wikipedia.org",
        "article_title": "AI_agent",
        "metric": "daily-pageviews-growth-v1"
      },
      "topic_b": {
        "topic_id": "gaming",
        "source_id": "wikimedia-pageviews-v1",
        "project": "en.wikipedia.org",
        "article_title": "Video_game",
        "metric": "daily-pageviews-growth-v1"
      },
      "observation_start": "1759990000000000000",
      "observation_end": "1759993600000000000",
      "formula": "growth_comparison_v1",
      "min_baseline_views": "1000",
      "tie_tolerance_bps": 50,
      "tie_policy": "void"
    }
  }
}
```

Outcome `0` always means `choices[0]` / Topic A; outcome `1` means
`choices[1]` / Topic B.

Battle validation is deterministic and atomic:

- Both topics need valid `topic_id`, `source_id`, `project`, `article_title`
  and `metric` values.
- Topics must be distinct by `topic_id` and `article_title`.
- Both topics must use the **same** `source_id`, `project` and `metric`.
- The market-level `source_id` must equal the shared topic source.
- `observation_start < observation_end` and
  `observation_end <= resolve_after`. The observation window is a single shared
  field, so both topics necessarily use the same window. Replay markets may use
  a historical window.
- `min_baseline_views > 0`.
- `tie_tolerance_bps <= 10000` (absolute growth-difference threshold in basis
  points).
- `formula` must be the supported frozen version `growth_comparison_v1`.
- `tie_policy` must be `void`.

Unknown enum values, unknown fields, missing topic fields and malformed JSON are
rejected during deserialization; semantic failures panic before any state is
written. Error codes are in section 12.

### 4.3 Immutability

There is no market update method. Every configuration field above is written
once at creation. Only lifecycle fields (status, outcome, evidence hash, void
reason, resolution kind, accounting totals) change afterwards. A fresh S2
deployment is required; S1 state is not migrated because the stored `Market`
layout gained fields.

## 5. Entering a position (NEP-141)

Both modes use the identical deposit path:

```json
ft_transfer_call(
  receiver_id = "<market contract>",
  amount = "10000000",
  msg = "{\"market_id\":\"battle-ai-vs-gaming\",\"outcome\":0}"
)
```

Attach exactly 1 yoctoNEAR to the token call and enough gas for the chain
(100 TGas recommended). The market implements:

```rust
ft_on_transfer(sender_id: AccountId, amount: U128, msg: String) -> PromiseOrValue<U128>
```

Rules:

- The token contract must equal the configured collateral token.
- `msg` must contain exactly `market_id` and `outcome` (unknown fields are
  rejected) and be ≤ 512 bytes.
- The market must be Open, inside its entry window, unpaused, and `amount` must
  be ≥ `min_entry_amount` and > 0. `outcome` must be 0 or 1.
- On success the market records the stake and returns `U128(0)`.
- On any rejection the market returns `U128(amount)`, and the token's
  `ft_resolve_transfer` refunds the sender.

Rejection reasons: `wrong_token`, `malformed_message`, `unknown_market`,
`entries_paused`, `market_not_open`, `before_open`, `after_close`,
`amount_zero`, `amount_below_minimum`, `invalid_outcome`, `amount_overflow`.
A rejected entry cannot create a position or change totals.

## 6. Lifecycle and resolution

```text
Open --(time, close_market / resolve)--> Closed --(resolver winner)--> Resolved
  |                                          |
  +---------------- (owner/resolver void) ----+--> Voided
  |
  +---------------- (resolver tie) ---------------> Voided (resolution_kind = tie)
```

A market can be resolved directly from Open once `now >= resolve_after`.

| Method | Caller | Guard | Effect |
| --- | --- | --- | --- |
| `close_market(market_id)` | anyone | `now >= close_at` | Open → Closed |
| `resolve_market(market_id, winning_outcome, evidence_hash)` | resolver | `now >= resolve_after`, winning pool > 0, valid digest | Resolved; outcome frozen |
| `resolve_tie(market_id, evidence_hash)` | resolver | Trend Battle, `now >= resolve_after`, tie policy void, valid digest | Voided with `resolution_kind = tie`; refunds |
| `void_market(market_id, reason_hash)` | owner or resolver | not final, valid digest | Voided with `resolution_kind = void`; refunds |
| `claim(market_id)` | participant | market Resolved or Voided | Starts payout/refund transfer |
| `claim_refund(market_id)` | participant | market Voided only | Starts refund transfer |

### Winner resolution

`resolve_market` records the winning side and commits `evidence_hash`. It is
idempotent when called again with the exact same outcome and evidence; a
conflicting outcome or evidence is rejected. Resolution with an empty winning
side is rejected (`ERR_NO_WINNING_STAKE`): the resolver must void instead, so no
winner is manufactured.

### Tie resolution

`resolve_tie` is the precommitted battle tie path. The resolver asserts that
the measured growth difference is within the frozen `tie_tolerance_bps` and
commits the calculation evidence. The contract:

- requires Trend Battle mode and the VOID tie policy;
- records `status = voided`, `resolution_kind = tie`, `evidence_hash`, no
  winning outcome and **no winner**;
- makes every position refundable through `claim` / `claim_refund`;
- is idempotent for identical evidence; a different evidence hash is rejected;
- can never run after a winner was resolved, and a tie-voided market can never
  later be resolved to a winner.

**Trust boundary:** the contract stores the tolerance and enforces the tie
outcome path, but it cannot verify external pageview data. The resolver must
call `resolve_tie` when the difference is within tolerance. S3's oracle and
evidence pipeline reduce this trust; S2 deliberately does not implement it. The
evidence hash is a commitment, not proof that the source is truthful.

## 7. Payouts, refunds and dust

For a resolved market with total escrow `T` and winning pool `W`:

```text
payout(account) = floor(stake_on_winning_side * T / W)
```

- Fees are zero.
- If only the winning side is funded, each winner receives their own stake
  back; no profit is manufactured.
- If both sides are funded, winners share the full pool pro rata, floored to
  integer base units.
- Rounding remainders ("dust") stay locked in the contract and are reported via
  `unclaimed_reserve`. S2 has no sweep function.
- A void (manual or tie) refunds each position its original total stake, once.
- `claimable` is `0` while a transfer is pending and after payment. A second
  claim cannot transfer again.

Example: Topic A pool = 110,000,000, Topic B pool = 50,000,000, escrow =
160,000,000. If A wins, the A holder receives
`floor(110,000,000 * 160,000,000 / 110,000,000) = 160,000,000`.

## 8. Claim safety and gas

`claim` / `claim_refund`:

1. Verify final status, position and claimability; reject if a transfer is
   pending.
2. Persist `pending_amount` / `pending_total` before creating a promise.
3. Call the collateral token's `ft_transfer` with 1 yoctoNEAR.
4. Chain a private callback with 20 TGas.
5. On success clear pending and increase `claimed_total` / `paid_total`.
6. On failure clear pending only; the escrow never left, so retry is safe.

The callback is `#[private]` and additionally asserts
`predecessor == current_account_id`. Internal gas is 25 + 20 TGas, so attach at
least 60 TGas (100 recommended) to claim transactions.

Known limitation: if the callback receipt itself runs out of gas after a
successful transfer, a pending amount could remain stuck. There is intentionally
no admin override that can move escrow. A bounded recovery mechanism is a later
security slice.

## 9. Views

Amounts and timestamps are JSON strings. Account IDs are strings.

| View | Returns |
| --- | --- |
| `get_market(market_id)` | `MarketView \| null` |
| `get_position(market_id, account_id)` | `PositionView \| null` |
| `get_market_totals(market_id)` | `MarketTotalsView \| null` |
| `get_claimable(market_id, account_id)` | `U128` (string), 0 while pending |
| `get_contract_config()` | `ConfigView` |
| `get_market_count()` | `u64` |
| `list_markets(from_index, limit)` | `MarketView[]` (limit capped at 50) |

`MarketView` fields: `market_id`, `mode` (`trend_trading|trend_battle`),
`question`, `choices`, `source_id`, `rule_hash`, `open_at`, `close_at`,
`resolve_after`, `invalidation_policy`, `status` (`open|closed|resolved|voided`),
`entries_open`, `entries_paused`, `totals` (`[U128; 2]`), `escrow_total`,
`paid_total`, `pending_total`, `unclaimed_reserve`, `winning_outcome`,
`winning_choice`, `evidence_hash`, `void_reason_hash`, `created_at`,
`resolved_at`, `voided_at`, `fee_bps` (always 0), `resolution_kind`
(`winning_outcome|void|tie|null`), and `battle` (null for Trend Trading).

`battle` fields: `topic_a`, `topic_b` (each with `topic_id`, `source_id`,
`project`, `article_title`, `metric`), `observation_start`, `observation_end`,
`formula`, `min_baseline_views`, `tie_tolerance_bps`, `tie_policy`.

`PositionView` fields: `market_id`, `account_id`, `stakes` (`[U128; 2]`),
`total_stake`, `claimed_total`, `pending_amount`, `claimable`, `claim_state`
(`open|pending|claimable|claimed|not_eligible`).

`MarketTotalsView` fields: `market_id`, `status`, `resolution_kind`, `totals`,
`winning_pool`, `escrow_total`, `paid_total`, `pending_total`,
`unclaimed_reserve`.

`ConfigView` fields: `owner`, `operator`, `resolver`, `collateral_token`,
`min_entry_amount`, `entries_paused`, `market_count`, `fee_bps`.

## 10. Events

NEP-297-shaped JSON logs with `standard = "notch-market"` and
`version = "1.0.0"`:

- `market_created`, `position_entered`, `entry_rejected`
- `market_closed`, `market_resolved`, `market_tie_voided`, `market_voided`
- `claim_requested`, `claim_settled`, `claim_failed`
- `entries_paused_updated`, `config_updated`

## 11. Error codes (panics)

Authorization: `ERR_NOT_OWNER`, `ERR_NOT_OPERATOR`, `ERR_NOT_RESOLVER`,
`ERR_NOT_AUTHORIZED`, `ERR_ONLY_SELF`.

Creation/config: `ERR_MIN_ENTRY_ZERO`, `ERR_ALREADY_INITIALIZED`,
`ERR_INVALID_MARKET_ID`, `ERR_MARKET_EXISTS`, `ERR_INVALID_QUESTION`,
`ERR_INVALID_CHOICES`, `ERR_INVALID_SOURCE_ID`, `ERR_INVALID_RULE_HASH`,
`ERR_INVALID_TIME_WINDOW`, `ERR_MARKET_ALREADY_CLOSED`,
`ERR_INVALID_RESOLVE_TIME`, `ERR_INVALID_INVALIDATION_POLICY`,
`ERR_ENTRIES_PAUSED`.

Battle creation: `ERR_MISSING_BATTLE_CONFIG`, `ERR_UNEXPECTED_BATTLE_CONFIG`,
`ERR_INVALID_TOPIC_ID`, `ERR_INVALID_TOPIC_SOURCE`, `ERR_INVALID_PROJECT`,
`ERR_INVALID_ARTICLE_TITLE`, `ERR_INVALID_METRIC`,
`ERR_TOPICS_NOT_DISTINCT`, `ERR_INCOMPATIBLE_TOPICS`, `ERR_SOURCE_MISMATCH`,
`ERR_INVALID_OBSERVATION_WINDOW`, `ERR_OBSERVATION_AFTER_RESOLVE`,
`ERR_INVALID_MIN_BASELINE`, `ERR_INVALID_TIE_TOLERANCE`,
`ERR_INVALID_TIE_POLICY`, `ERR_INVALID_BATTLE_FORMULA`.

Lifecycle: `ERR_MARKET_NOT_FOUND`, `ERR_ENTRY_WINDOW_OPEN`,
`ERR_MARKET_FINALIZED`, `ERR_INVALID_OUTCOME`, `ERR_INVALID_EVIDENCE_HASH`,
`ERR_RESOLVE_TOO_EARLY`, `ERR_NO_WINNING_STAKE`, `ERR_ALREADY_RESOLVED`,
`ERR_INVALID_REASON_HASH`, `ERR_ALREADY_VOIDED`, `ERR_MARKET_VOIDED`,
`ERR_MARKET_RESOLVED`, `ERR_NOT_BATTLE_MARKET`.

Claims: `ERR_MARKET_NOT_SETTLED`, `ERR_MARKET_NOT_VOIDED`, `ERR_NO_POSITION`,
`ERR_CLAIM_PENDING`, `ERR_NOTHING_TO_CLAIM`, `ERR_INCONSISTENT_STATE`,
`ERR_OVERFLOW`, `ERR_MATH_DIVISION_BY_ZERO`, `ERR_MATH_OVERFLOW`.

Deposits never panic on user error; they refund and emit `entry_rejected`.

## 12. Build, test and integration suite

```bash
cargo test -p notch-market                     # 109 unit tests
cargo build --release --target wasm32-unknown-unknown -p notch-market
sha256sum target/wasm32-unknown-unknown/release/notch_market.wasm
```

Windows: `aws-lc-sys` (pulled by near-sdk's `unit-testing` feature) needs NASM
for the unit-test build. Either install NASM or set
`AWS_LC_SYS_PREBUILT_NASM=1`.

The unit suite uses the real near-sdk mocked runtime, including mocked
`PromiseResult` values for callback success and failure. It covers all S1
Trend Trading tests plus battle validation, both winners, ties, duplicate
resolution/claims, cross-mode conservation and failed-transfer recovery.

### near-workspaces integration tests

`near-workspaces` supports linux-x86_64, linux-aarch64 and darwin-arm64. On
Windows run inside WSL Ubuntu or Linux CI.

```bash
# from the repository root
cargo build --release --target wasm32-unknown-unknown -p notch-market
mkdir -p contracts/market/res
cp target/wasm32-unknown-unknown/release/notch_market.wasm contracts/market/res/notch_market.wasm
(cd tests/test-token && cargo build --release --target wasm32-unknown-unknown)
(cd tests/integration && cargo test --test market_flow -- --nocapture)
```

Three sandbox tests deploy a real NEP-141 token and the market:

1. `trend_trading_end_to_end`
2. `void_refund_and_failed_transfer_recovery`
3. `trend_battle_flow` — battle entry, Topic B winner payout, duplicate claim
   rejection, tie → VOID → refunds, idempotent tie evidence, conflicting tie and
   retroactive winner rejection.

## 13. Testnet collateral compatibility

Verified on 2026-11-11 against live testnet (raw evidence:
[`docs/s2_collateral_check.txt`](../../docs/s2_collateral_check.txt)):

| Item | Value |
| --- | --- |
| Tidepool token list | `GET https://www.usetidepool.tech/v0/tokens` |
| Intended test-USDC | `usdc.tidepool-sandbox.testnet` |
| Network | NEAR testnet (NEP-141) |
| Standard | `ft-1.0.0` |
| Symbol / name | `USDC` / `Tidepool Testnet USDC (no value)` |
| Decimals | **6** |
| Total supply at check | 2,005,900.000000 USDC |
| Account | exists; code hash `DgV3WsKJsGtCjNWxYzFvi599szo7oojkKXWCoGBBAHwj` |
| Storage bounds | min = max = **0.00125 NEAR** per account |
| `ft_transfer` / `ft_transfer_call` | present (read-only call panics on missing 1 yoctoNEAR) |
| `storage_deposit` | present (read-only call panics on missing storage deposit) |
| `ft_resolve_transfer` | present |
| `storage_balance_of(market.notch-dev.testnet)` | registered: total 0.00125 NEAR, available 0 |
| `storage_balance_of(notch-dev.testnet)` | registered: total 0.00125 NEAR, available 0 |

The token has 6 decimals, so configure `min_entry_amount` in base units (for
example `"1000000"` = 1 USDC). The market account was registered with the token
via `storage_deposit`; the registration transaction is
`7bCin9AdmyG4zGVnfATrDXe1fmjZ1aUut9tCpFHgARX3`.

**Live deposit still unverified:** the market and the development wallet are
registered, but no funded `ft_transfer_call` into the deployed contract has been
executed yet. The development wallet has 0 test USDC because the Tidepool
faucet enforces an account-age restriction. Deployment is complete; the remaining
live check is a funded deposit, resolution and payout. Current state is in
[`docs/TESTNET_DEPLOYMENT.md`](../../docs/TESTNET_DEPLOYMENT.md).

Tidepool is a community testnet sandbox, not official NEAR Intents. Its tokens
have **no value**. Claim test tokens at <https://app.usetidepool.tech/faucet>
(100 test USDC+USDT per claim, one claim per address every 7 days).

## 14. Testnet deployment status

**Deployed on NEAR testnet:** `market.notch-dev.testnet`.

| Field | Value |
| --- | --- |
| Deployed code hash | `BGauRHWiPwFCbqrXJSzSAYG1bGVyMUidSxEvkionp1LK` |
| Deployed code SHA-256 | `9892eaa0c113378ca188137d6565d444ff6a8794bda3a596ce1fdcbb692f0f08` |
| Deployment transaction | `EFJvJVmBMWAh4Rqaxh7s2uCn72Hm1uXV3yc9zmEaEeDj` |
| USDC registration transaction | `7bCin9AdmyG4zGVnfATrDXe1fmjZ1aUut9tCpFHgARX3` |
| Collateral | `usdc.tidepool-sandbox.testnet` (6 decimals) |
| Owner / operator / resolver | `notch-dev.testnet` |
| Minimum entry | `1000000` base units (1 test USDC) |
| Market count at verification | 0 |

The deployed code was fetched with `view_code` and matches the S2 artifact
byte-for-byte. The deployment was not repeated or reinitialized. Current
operational details, wallet state and the first market proposal are in
[`docs/TESTNET_DEPLOYMENT.md`](../../docs/TESTNET_DEPLOYMENT.md).

The first Trend Trading market is prepared and signed-previewed but **not
broadcast**: it is awaiting explicit approval. Tidepool test USDC is not yet in
the development wallet because the faucet enforces an account-age restriction.

### Manual deployment procedure (fresh deployment only)

The live deployment is recorded above and in
[`docs/TESTNET_DEPLOYMENT.md`](../../docs/TESTNET_DEPLOYMENT.md). The example
below is for a new account and must not be used to overwrite the live market
contract.

```bash
# 1. Install the current CLI and create a faucet-funded testnet account
cargo install near-cli-rs --locked
near account create-account sponsor-by-faucet-service notch-market.testnet \
  autogenerate-new-keypair save-to-legacy-keychain network-config testnet create

# 2. Deploy S2 fresh (do not reuse S1 state) and initialize with Tidepool USDC
near contract deploy notch-market.testnet \
  use-file contracts/market/res/notch_market.wasm \
  with-init-call new json-args \
  '{"owner":"<owner.testnet>","operator":"<operator.testnet>","resolver":"<resolver.testnet>","collateral_token":"usdc.tidepool-sandbox.testnet","min_entry_amount":"1000000"}' \
  prepaid-gas '100 Tgas' attached-deposit '0 NEAR' \
  network-config testnet sign-with-keychain send

# 3. Register the market account with the collateral token (minimum 0.00125 NEAR)
near contract call-function usdc.tidepool-sandbox.testnet storage_deposit \
  json-args '{"account_id":"notch-market.testnet","registration_only":true}' \
  prepaid-gas '30 Tgas' attached-deposit '0.002 NEAR' \
  network-config testnet sign-with-keychain send

# 4. Verify config and token metadata
near contract call-function notch-market.testnet get_contract_config \
  json-args '{}' prepaid-gas '30 Tgas' attached-deposit '0 NEAR' \
  network-config testnet sign-with-keychain send
near contract call-function usdc.tidepool-sandbox.testnet ft_metadata \
  json-args '{}' prepaid-gas '30 Tgas' attached-deposit '0 NEAR' \
  network-config testnet sign-with-keychain send
```

Then, with faucet test USDC in test wallets:

1. Create one Trend Trading and one Trend Battle market as the operator.
2. Call `ft_transfer_call` into the market with the message schema above.
3. Close, resolve (or `resolve_tie`) and claim.
4. Record account IDs, wasm hash, deployment tx, deposit tx, resolution tx and
   claim tx in `docs/S2_VERIFICATION.md`.

## 15. Known limitations and S3 prerequisites

S2 limitations:

- The resolver is trusted for the outcome and for deciding that a battle result
  is within the frozen tie tolerance; no oracle verifies external data yet.
- Battle configuration is immutable; there is no update or migration method.
- S2 changes the stored `Market` layout; deploy fresh rather than upgrading an
  S1 deployment.
- No fees, leverage, liquidation, secondary trading or partial refunds.
- No token sweep; rounding dust and stray direct transfers remain locked.
- Storage costs are paid by the contract account, not by users.

S3 prerequisites:

- Wikimedia pageviews snapshot worker with canonical JSON and digesting.
- Deterministic growth/tie calculation matching `growth_comparison_v1`,
  including minimum-baseline and missing-data policies.
- Authorized oracle submission pipeline that calls `resolve_market` or
  `resolve_tie` idempotently after freshness checks.
- Evidence verification endpoint/page linking the onchain digest to raw data.
- Testnet deployment and live collateral deposit completed first.
