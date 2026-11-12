# S2.5 — First verified onchain markets

Date: 2026-11-12 (UTC)
Network: NEAR testnet only. No real funds.

## Status

| Stage | Status |
| --- | --- |
| Repository/chain preflight | **PASS** |
| S3B rules and evidence re-verified | **PASS** |
| Short-window timing correction prepared | **PASS — 90-minute windows derived from live chain time** |
| Rule operator approval | **PASS — both rules APPROVED by `notch-dev.testnet`** |
| Trend Trading market creation | **EXECUTED** — `2k4v9StY83xsyqAkR36Zke92HxA6U6UbXejVZGDDNxdJ` |
| Trend Battle market creation | **EXECUTED** — `2suiYW9xYGPPYiX3DpHuuQ7NAUrxGuTVxvyrctibvev8` |
| Test USDC funding | **PASS — 100,000,000 base units (100 test USDC)** |
| Position deposits | **EXECUTED — 1 test USDC on UP and 1 test USDC on Bitcoin** |
| Onchain resolution | **EXECUTED — UP and Bitcoin; onchain evidence hashes match** |
| Claim/payout | **EXECUTED — 1 test USDC per market; duplicate claim rejected** |
| Current market count | **2** |
| Transactions submitted by this milestone | **10 successful + 1 expected duplicate-claim rejection** |

The short-window rules are in `var/oracle_s2_5_short/oracle.sqlite3`; old S3B
rules/evidence remain in `var/oracle_live_final/oracle.sqlite3`. New evidence
receipts are in `docs/evidence/s2_5_short_evidence_*.json`.

Both short-window markets were created, funded, closed, resolved and claimed on
2026-11-12. The complete lifecycle and transaction hashes are in section 11. No
private key or signature is recorded here.

> **2026-11-12 short-window correction:** The long-window replay rules in
> sections 2–9 below are preserved for audit but are **superseded**. The executed
> hackathon demonstration uses the 90-minute short-window variants in
> [section 10](#10-short-window-timing-correction-2026-11-12): Nvidia trend rule
> `sha256:79c8f464…` and Bitcoin/ChatGPT battle rule `sha256:b6a5c889…`. Both new
> rules were approved and executed; see
> [section 11](#11-executed-onchain-demonstration-2026-11-12). Sections 2–10
> preserve the pre-execution review and preparation history.

## 1. Current contract state

| Field | Value |
| --- | --- |
| Contract | `market.notch-dev.testnet` |
| Owner / operator / resolver | `notch-dev.testnet` |
| Collateral | `usdc.tidepool-sandbox.testnet` |
| Deployed code hash | `BGauRHWiPwFCbqrXJSzSAYG1bGVyMUidSxEvkionp1LK` |
| Deployed code SHA-256 | `9892eaa0c113378ca188137d6565d444ff6a8794bda3a596ce1fdcbb692f0f08` |
| Local S2 artifact | Same size and SHA-256 — byte-for-byte compatible |
| Market count | **2** — both resolved and claimed |
| Entries paused | `false` |
| Minimum entry | `1000000` base units (1 test USDC) |
| Contract account balance | ~6.9965 NEAR |
| Contract storage usage | 451,928 bytes |
| Latest chain block | 277,321,649 at `2026-11-12T05:48:19Z` |
| `market.notch-dev.testnet` USDC storage | Registered — 0.00125 NEAR |
| `notch-dev.testnet` USDC storage | Registered — 0.00125 NEAR |
| `notch-dev.testnet` NEAR balance | **2.9854050633191377 NEAR** (after execution) |
| `notch-dev.testnet` USDC balance | **100,000,000** base units (100 test USDC; restored after claims) |
| S3B short-window markets | Both created, resolved and claimed — section 11 |

The contract was not redeployed, reinitialized or modified.

## 2. Market review — approved and executed

Both markets are **HISTORICAL REPLAY / KNOWN-OUTCOME DEMONSTRATIONS**, not
future forecasts. The questions say so explicitly. The source observations are
real Wikimedia daily pageviews for 2026-11-03 and 2026-11-10.

### A. Nvidia replay — Trend Trading

| Field | Value |
| --- | --- |
| Market ID | `s3b-replay-trend-nvidia-20261103-20261110` |
| Mode | `trend_trading` |
| Question | `HISTORICAL REPLAY (not a forecast): Will daily en.wikipedia.org pageviews for Nvidia grow by at least 13.50% on the full UTC day 2026-11-10 versus the full UTC day 2026-11-03? (Wikimedia Pageviews, all-access, user)` |
| Observation | 2026-11-03 baseline / 2026-11-10 target, historical UTC days |
| Actual observations | 4,743 → 123,851 views |
| Growth | **251,123 bps** (2,511.23%) |
| Threshold | 1,350 bps (13.50%) |
| Calculated result | **UP** (outcome 0) |
| Evidence digest | `sha256:0c5ede6be9542b2d161601d6e5e6205c725dc8bf7ad9a488a63911c5f22ddbb2` |
| Canonical rule hash | `sha256:1c42a2d04a29c5ba2a0bde3cb8e8a65d06292c965180143022cb07e979c6a47b` |
| Entry opens | `2026-11-12T03:00:00Z` |
| Entries close | `2026-11-15T23:59:00Z` |
| Resolution eligible | `2026-11-17T12:00:00Z` |
| Rule status | **APPROVED — executed 2026-11-12** |
| Exact create payload | `docs/evidence/s3b_create_args_replay_trend_nvidia.json` |

### B. Bitcoin vs ChatGPT replay — Trend Battle

| Field | Value |
| --- | --- |
| Market ID | `s3b-replay-battle-btc-chatgpt-20261103-20261110` |
| Mode | `trend_battle` |
| Question | `HISTORICAL REPLAY (not a forecast): Which topic had higher normalized Wikimedia pageview growth from the full UTC day 2026-11-03 to the full UTC day 2026-11-10: Bitcoin or ChatGPT? A difference within 930 bps is a tie and voids the market.` |
| Observation | 2026-11-03 / 2026-11-10, historical UTC days |
| Bitcoin observed | 3,751 → 4,359 views; **+1,620 bps** |
| ChatGPT observed | 117,118 → 59,377 views; **-4,931 bps** |
| Difference | **6,551 bps** |
| Tie tolerance | 930 bps; tie policy VOID |
| Calculated result | **TOPIC_A — Bitcoin** (outcome 0) |
| Evidence digest | `sha256:cef387d5905985f5bf2644d2cb4daad735dfd8b076fc429a598d199927a60e12` |
| Canonical rule hash | `sha256:64a41270b9b68a7c33a972001adc1122b35c0877d1e04692f2cf2742fad1c19d` |
| Entry opens | `2026-11-12T03:00:00Z` |
| Entries close | `2026-11-15T23:59:00Z` |
| Resolution eligible | `2026-11-17T12:00:00Z` |
| Rule status | **APPROVED — executed 2026-11-12** |
| Exact create payload | `docs/evidence/s3b_create_args_replay_battle_bitcoin_chatgpt.json` |

### Verification performed

- Rule hashes match the exact create payloads and the stored S3B rules.
- `validate_rule` and `validate_create_args` pass for both.
- Evidence receipts independently verify; observation hashes, raw-response
  hashes, formulas and outcomes recompute.
- The current chain time `2026-11-12T03:23:54Z` is inside the entry window
  (`03:00` open, `23:59` Nov 15 close); no proposed window has expired.
- Exact creation commands were `display`-signed by `notch-dev.testnet` with the
  keychain, showing the correct receiver, method, args, 100 Tgas and 0 NEAR.
  **They were not broadcast.**

## 3. Creation evidence

**None — transactions were not broadcast.** No market ID has an onchain
transaction hash yet.

Exact commands to run after explicit approval:

```bash
# Trend Trading
near contract call-function as-transaction market.notch-dev.testnet create_market \
  file-args docs/evidence/s3b_create_args_replay_trend_nvidia.json \
  prepaid-gas '100 Tgas' attached-deposit '0 NEAR' \
  sign-as notch-dev.testnet network-config testnet sign-with-keychain send

# Trend Battle
near contract call-function as-transaction market.notch-dev.testnet create_market \
  file-args docs/evidence/s3b_create_args_replay_battle_bitcoin_chatgpt.json \
  prepaid-gas '100 Tgas' attached-deposit '0 NEAR' \
  sign-as notch-dev.testnet network-config testnet sign-with-keychain send
```

After each send, verify and record:

```bash
near contract call-function as-read-only market.notch-dev.testnet get_market \
  json-args '{"market_id":"s3b-replay-trend-nvidia-20261103-20261110"}' \
  network-config testnet now

near contract call-function as-read-only market.notch-dev.testnet get_market_count \
  json-args '{}' network-config testnet now
```

Expected `get_market`: mode, question, choices, source, exact `rule_hash`, open/
close/resolve timestamps, status `open`; zero totals. Do not retry a failed or
uncertain `create_market` without first checking `get_market` and
`get_market_count`.

## 4. Test USDC funding

| Item | Value |
| --- | --- |
| Developer wallet USDC storage | Registered |
| Market contract USDC storage | Registered |
| Developer wallet USDC balance | **0** |
| Tidepool token | `usdc.tidepool-sandbox.testnet`, 6 decimals, no value |
| Faucet | <https://app.usetidepool.tech/faucet> |

The wallet is now roughly four hours old (deployment at
`2026-11-11T23:15:40Z`; current chain time `2026-11-12T03:23:54Z`), so the
previous account-age rejection should no longer apply. The faucet was **not
called again** by this milestone. The user must claim once through the official
site:

1. Open <https://app.usetidepool.tech/faucet>.
2. Use/enter `notch-dev.testnet`.
3. Claim the free test USDC once. Test tokens have no value; do not send mainnet
   assets.
4. Verify:

```bash
near contract call-function as-read-only usdc.tidepool-sandbox.testnet \
  ft_balance_of json-args '{"account_id":"notch-dev.testnet"}' \
  network-config testnet now
```

No balance was fabricated. The faucet has a one-claim-per-address/7-day limit and
must not be abused.

## 5. Position deposits

**Not executed** because the USDC balance is 0 and no market exists yet.

After funding and market creation, the smallest valid position is 1 test USDC
(`1000000` base units). For both replay markets the known result is on outcome
`0`:

```bash
# Nvidia trend UP (outcome 0), 1 test USDC
near contract call-function as-transaction usdc.tidepool-sandbox.testnet ft_transfer_call \
  json-args '{"receiver_id":"market.notch-dev.testnet","amount":"1000000","msg":"{\"market_id\":\"s3b-replay-trend-nvidia-20261103-20261110\",\"outcome\":0}"}' \
  prepaid-gas '100 Tgas' attached-deposit '1 yoctoNEAR' \
  sign-as notch-dev.testnet network-config testnet sign-with-keychain send

# Bitcoin battle TOPIC_A (outcome 0), 1 test USDC
near contract call-function as-transaction usdc.tidepool-sandbox.testnet ft_transfer_call \
  json-args '{"receiver_id":"market.notch-dev.testnet","amount":"1000000","msg":"{\"market_id\":\"s3b-replay-battle-btc-chatgpt-20261103-20261110\",\"outcome\":0}"}' \
  prepaid-gas '100 Tgas' attached-deposit '1 yoctoNEAR' \
  sign-as notch-dev.testnet network-config testnet sign-with-keychain send
```

If only the developer wallet is funded, each market is one-sided. Claiming will
prove stake recovery/claimability, **not** a profitable multi-party market. No
opposing activity will be manufactured.

Verify with `get_position` and `get_market_totals`. Each deposit requires
separate approval before sending.

## 6. Oracle resolution and evidence

The S3B evidence is complete and verified, but the market cannot resolve until
`2026-11-17T12:00:00Z` (both replay markets). The onchain markets do not exist,
so no resolution plan can be `PREPARED` yet.

After creation, funding, the close deadline, and `resolve_after`, the exact
read-only preparation command is:

```bash
python -m services.oracle --data-dir var/oracle_live_final prepare-resolution \
  --rule-hash sha256:1c42a2d04a29c5ba2a0bde3cb8e8a65d06292c965180143022cb07e979c6a47b \
  --evidence-digest sha256:0c5ede6be9542b2d161601d6e5e6205c725dc8bf7ad9a488a63911c5f22ddbb2 \
  --onchain --now 2026-11-17T13:00:00Z
```

For the battle:

```bash
python -m services.oracle --data-dir var/oracle_live_final prepare-resolution \
  --rule-hash sha256:64a41270b9b68a7c33a972001adc1122b35c0877d1e04692f2cf2742fad1c19d \
  --evidence-digest sha256:cef387d5905985f5bf2644d2cb4daad735dfd8b076fc429a598d199927a60e12 \
  --onchain --now 2026-11-17T13:00:00Z
```

Expected prepared calls:

```json
{"market_id":"s3b-replay-trend-nvidia-20261103-20261110","winning_outcome":0,"evidence_hash":"sha256:0c5ede6be9542b2d161601d6e5e6205c725dc8bf7ad9a488a63911c5f22ddbb2"}
{"market_id":"s3b-replay-battle-btc-chatgpt-20261103-20261110","winning_outcome":0,"evidence_hash":"sha256:cef387d5905985f5bf2644d2cb4daad735dfd8b076fc429a598d199927a60e12"}
```

The preparation layer will verify the live market's rule hash, source,
timestamps, battle config, status and collateral before returning `PREPARED`. It
will also verify the winning side has nonzero stake. Do not submit a guessed or
altered outcome.

## 7. Claim and payout

**Not executed.** No market, position or resolution exists.

After a successful resolution, each participant can call `claim`; the contract
uses `ft_transfer` plus a private callback and only marks payment after the
callback succeeds. The claim transaction requires ~100 Tgas. For a one-sided
market, the claim returns the staked 1 test USDC; it does not demonstrate profit.

Post-claim checks:

- `get_position` → `claim_state: claimed`, `claimed_total` correct.
- `get_market_totals` → `paid_total`, `pending_total`, `unclaimed_reserve`
  conserve escrow.
- Wallet USDC before/after.
- A duplicate claim fails with `ERR_NOTHING_TO_CLAIM`.

## 8. Evidence verification

```bash
python -m services.oracle --data-dir var/oracle_live_final verify-evidence \
  var/oracle_live_final/evidence/s3b-replay-trend-nvidia-20261103-20261110.0c5ede6be9542b2d161601d6e5e6205c725dc8bf7ad9a488a63911c5f22ddbb2.json

python -m services.oracle --data-dir var/oracle_live_final verify-evidence \
  var/oracle_live_final/evidence/s3b-replay-battle-btc-chatgpt-20261103-20261110.cef387d5905985f5bf2644d2cb4daad735dfd8b076fc429a598d199927a60e12.json
```

Both currently return `valid: true`, with the expected `rule_hash` and outcome.
The resolver is trusted by the S2 contract; the evidence digest proves integrity
of the recorded source payload and calculation, not organic attention or
resolver honesty.

## 9. Pre-execution blockers and next actions (resolved 2026-11-12)

### Blockers

1. **Explicit approval** for rule approval and the two `create_market`
   transactions was not granted. No transaction was broadcast.
2. **USDC balance is 0.** The wallet must use the Tidepool faucet once; market
   creation does not require USDC, but positions do.
3. **Time gate.** Both replay markets resolve no earlier than
   `2026-11-17T12:00:00Z`; claims follow successful resolution. The entry window
   closes `2026-11-15T23:59:00Z`.
4. **No markets exist onchain** (`market_count: 0`), so resolution preparation
   is correctly blocked and no claim is possible.

### Exact next actions

1. Operator approves this review (rules and creation; positions separately).
2. Approve both rules locally:
   ```bash
   python -m services.oracle --data-dir var/oracle_live_final approve-rule \
     sha256:1c42a2d04a29c5ba2a0bde3cb8e8a65d06292c965180143022cb07e979c6a47b \
     --reason "approved S2.5 replay market" --operator notch-dev.testnet
   python -m services.oracle --data-dir var/oracle_live_final approve-rule \
     sha256:64a41270b9b68a7c33a972001adc1122b35c0877d1e04692f2cf2742fad1c19d \
     --reason "approved S2.5 replay battle" --operator notch-dev.testnet
   ```
3. Broadcast the two creation commands above, verify `get_market` and
   `get_market_count`, and record tx hashes/explorer links.
4. Claim test USDC from the official faucet after the age restriction cleared;
   verify the wallet balance.
5. Deposit 1 USDC positions on the known winning sides after separate approval;
   verify positions/totals.
6. At/after `2026-11-17T12:00:00Z`, generate the prepared resolution calls with
   the oracle, review, approve, and submit from the resolver. Verify onchain
   outcome.
7. Claim the positions, verify balances and duplicate-claim protection.
8. Append every transaction hash and balance to this document and
   `docs/TESTNET_DEPLOYMENT.md`.

No S4 work, frontend work, contract redeployment or unapproved transaction was
started.

## 10. Short-window timing correction (2026-11-12)

### Previous timing (superseded)

The original replay rules closed on 2026-11-15 at 23:59 UTC and became
resolvable on 2026-11-17 at 12:00 UTC. The NEAR Hackathon deadline is
2026-11-14 at 23:59 UTC, so those timings could not support the required
create → fund → close → resolve → claim demonstration before submission.

The original rules and evidence are preserved:

| Original market | Original rule hash | Original evidence digest |
| --- | --- | --- |
| `s3b-replay-trend-nvidia-20261103-20261110` | `sha256:1c42a2d04a29c5ba2a0bde3cb8e8a65d06292c965180143022cb07e979c6a47b` | `sha256:0c5ede6be9542b2d161601d6e5e6205c725dc8bf7ad9a488a63911c5f22ddbb2` |
| `s3b-replay-battle-btc-chatgpt-20261103-20261110` | `sha256:64a41270b9b68a7c33a972001adc1122b35c0877d1e04692f2cf2742fad1c19d` | `sha256:cef387d5905985f5bf2644d2cb4daad735dfd8b076fc429a598d199927a60e12` |

They were **not modified**; their timings are superseded for the hackathon
demo.

### Contract timing constraints verified in source

`contracts/market/src/lib.rs`:

- `create_market` requires `open_at < close_at`, `close_at > now`, and
  `resolve_after >= close_at`.
- There is no minimum entry duration. Entry can start immediately
  (`open_at` may already be past at creation) and close can be 90 minutes later.
- `resolve_market` requires `now >= resolve_after`; the market need not be
  explicitly closed first.
- For battles, `observation_start < observation_end <= resolve_after`; historical
  observation dates are compatible with a future entry/close/resolution.
- No time gate was bypassed. All timings below are derived from the live testnet
  block time.

### Regenerated short-window rules

Live chain time at preparation: **2026-11-12T03:58:29Z**.

| Field | Trend Trading | Trend Battle |
| --- | --- | --- |
| New market ID | `s3b-short-trend-nvidia-20261112T040029Z` | `s3b-short-battle-btc-chatgpt-20261112T040029Z` |
| Mode | `trend_trading` | `trend_battle` |
| Observation | 2026-11-03 / 2026-11-10 historical | 2026-11-03 / 2026-11-10 historical |
| Known result | **UP** (4,743 → 123,851; 251,123 bps; threshold 1,350) | **TOPIC_A Bitcoin** (Bitcoin +1,620, ChatGPT −4,931; difference 6,551; tie 930) |
| New rule hash | `sha256:79c8f464a8cb4fe1c2cd42b636755c9d31c5ad87abe2bca84af3427ccb47d0a9` | `sha256:b6a5c88950744db167b02743ec5bab517d7dc0073911ef2dab478f55934c6e57` |
| New evidence digest | `sha256:583eac071d0b3d8a9ad661f02180c2d1c58fbac435e68b5c6346a28348257e06` | `sha256:ad15ea91fa97e32cc97e5dd94dc5db72a511e5fa980b1e8c7615b2db0ccd3e5d` |
| Entry opens | `2026-11-12T04:00:29Z` | `2026-11-12T04:00:29Z` |
| Entries close | `2026-11-12T05:30:29Z` | `2026-11-12T05:30:29Z` |
| Resolution eligible | `2026-11-12T05:35:29Z` | `2026-11-12T05:35:29Z` |
| Entry window | 90 minutes | 90 minutes |
| Rule status | **APPROVED** | **APPROVED** |

These timings leave room to resolve and claim on 2026-11-12, well before the
2026-11-14 submission deadline.

The preparation used the existing canonical rule builders and the same real
observations, thresholds, tie tolerance, source identities, formula versions and
settlement rules. Only the market IDs and contract timing changed. New evidence
receipts were built because the rule hash is part of the receipt; the historical
values and outcomes are unchanged.

New artifacts:

- `docs/evidence/s2_5_short_preparation.json`
- `docs/evidence/s2_5_short_create_args_trend_nvidia.json`
- `docs/evidence/s2_5_short_create_args_battle_bitcoin_chatgpt.json`
- `docs/evidence/s2_5_short_evidence_trend_nvidia.json`
- `docs/evidence/s2_5_short_evidence_battle_bitcoin_chatgpt.json`
- `scripts/prepare_s2_5_short_windows.py` (re-runnable from live chain time)

### Validation results

- `validate_rule` and `validate_create_args` pass for both new payloads.
- New evidence receipts verify independently (`verify-evidence` returns
  `valid: true`), with the expected outcomes `UP` and `TOPIC_A`.
- A deterministic replay of the preparation at the captured chain time produced
  the same new rule hashes and evidence digests.
- The short market IDs return `null` onchain (`market_count: 0`); no creation
  transaction was sent.
- Both create calls were `display`-signed by `notch-dev.testnet` with 100 Tgas
  and 0 NEAR deposit; the previews were **not broadcast** and no signed payload
  was retained.

### Funding status

- Development wallet USDC storage: registered.
- Market contract USDC storage: registered.
- Development wallet USDC balance: **0**.
- The account is now older than the three-hour faucet age gate; the faucet was
  not re-called.
- Official faucet: <https://app.usetidepool.tech/faucet>. Claim free test USDC
  once for `notch-dev.testnet`; test tokens have no value. Do not use mainnet
  assets or repeatedly call the faucet.

No position can be deposited until the wallet is funded. With only one funded
side, claims demonstrate stake recovery/claimability, not profit.

### Approval and window expiry

Explicit approval is required before:

1. approving either new DRAFT rule;
2. broadcasting the two `create_market` transactions;
3. depositing positions;
4. resolving and claiming.

The 90-minute window starts at `2026-11-12T04:00:29Z`. If approval or funding
arrives after `05:30:29Z`, **do not broadcast the expired payloads**; rerun:

```bash
python scripts/prepare_s2_5_short_windows.py
```

That derives a new open/close/resolve set from the then-current chain time and
writes new payloads. Old rules/evidence remain untouched.

## 11. Executed onchain demonstration (2026-11-12)

> **Current state.** Sections 2–10 preserve the pre-execution review and
> preparation history. This section records the completed lifecycle.

The funded-wallet continuation was treated as operator approval for the
prepared short-window markets. Both rules were approved locally by
`notch-dev.testnet`, then the complete **CREATE → DEPOSIT → CLOSE → RESOLVE →
CLAIM** flow was executed on NEAR testnet. The final claim completed before the
2026-11-14 submission deadline.

### Lifecycle transactions

| Step | Nvidia Trend Trading | Bitcoin/ChatGPT Trend Battle |
| --- | --- | --- |
| Create | `2k4v9StY83xsyqAkR36Zke92HxA6U6UbXejVZGDDNxdJ` | `2suiYW9xYGPPYiX3DpHuuQ7NAUrxGuTVxvyrctibvev8` |
| Deposit 1 test USDC | `CMLP8mVWgEZLHb2EXF29EXGSbvJjAbP9LSRC9WjVuXRB` | `6MSX3WrtgZ2pPAEr5McodeU9g8x3rq2Dkog7uRv9Nik6` |
| Close | `2q7oAYrCZN49n9PwKWXZNxhqxRQFef4z9jb9ytXzu7Xv` | `FrKG8vK1EN2FXWAgBDqPat7HmTa6AodRVxM4UdGTwd7X` |
| Resolve | `Bh7kDST6dhMDwz5gMfsjrmmmtpbZZsSvKkukjkGzL4u1` | `2tvcgQA4Y7wDHvFv3EaQ3WJNvwnsgZZLvyxfxm5hsqmH` |
| Claim | `C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr` | `C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU` |

All ten lifecycle transactions succeeded. Explorer pattern:
`https://explorer.testnet.near.org/transactions/<tx-hash>`.

### Creation and deposits

| Field | Trend Trading | Trend Battle |
| --- | --- | --- |
| Market ID | `s3b-short-trend-nvidia-20261112T040029Z` | `s3b-short-battle-btc-chatgpt-20261112T040029Z` |
| Created at | `2026-11-12T04:26:35.870270327Z` | `2026-11-12T04:26:51.021522982Z` |
| Entry window | `04:00:29.473464Z–05:30:29.473464Z` | same |
| Deposit | `1,000,000` base units on `UP` (outcome 0) | `1,000,000` base units on `Bitcoin` (outcome 0) |
| Deposit acceptance | Token `ft_transfer` + market `position_entered` event; `get_position` stakes `[1000000, 0]` | same, on Bitcoin |
| Market totals after deposit | `["1000000", "0"]`; escrow `1000000` | `["1000000", "0"]`; escrow `1000000` |

The token's outer `ft_transfer_call` return printed the transferred amount. The
market's `position_entered` event, `get_position`, `get_market_totals`, wallet
balance and market token balance confirm that the full amount was accepted and
that there was no refund.

USDC balances:

| Point | Wallet | Market contract |
| --- | --- | --- |
| Before | `100000000` | `0` |
| After both deposits | `98000000` | `2000000` |
| After both claims | `100000000` | `0` |

Both accounts remain registered for USDC storage.

### Settlement

| Field | Trend Trading | Trend Battle |
| --- | --- | --- |
| Rule hash | `sha256:79c8f464a8cb4fe1c2cd42b636755c9d31c5ad87abe2bca84af3427ccb47d0a9` | `sha256:b6a5c88950744db167b02743ec5bab517d7dc0073911ef2dab478f55934c6e57` |
| Evidence digest | `sha256:583eac071d0b3d8a9ad661f02180c2d1c58fbac435e68b5c6346a28348257e06` | `sha256:ad15ea91fa97e32cc97e5dd94dc5db72a511e5fa980b1e8c7615b2db0ccd3e5d` |
| Onchain evidence hash | matches | matches |
| Outcome | `UP` (growth 251,123 bps; threshold 1,350) | `TOPIC_A` Bitcoin (BTC +1,620; ChatGPT −4,931; difference 6,551; tie 930) |
| Winning outcome | `0` / `UP` | `0` / `Bitcoin` |
| Closed at | `2026-11-12T05:37:02.836273647Z` | `2026-11-12T05:37:13.128869670Z` |
| Resolved at | `2026-11-12T05:38:06.615121843Z` | `2026-11-12T05:38:28.510063258Z` |
| Resolution kind | `winning_outcome` | `winning_outcome` |

The resolution plans were generated by the existing S3B oracle with
`--onchain`; both returned `PREPARED` with no blockers or warnings. The
resolution evidence uses the same real historical Wikimedia observations as the
approved rules.

### Payouts and duplicate protection

| Field | Trend Trading | Trend Battle |
| --- | --- | --- |
| Claimable before claim | `1000000` | `1000000` |
| Claim transaction | `C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr` | `C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU` |
| Token transfer | `1,000,000` USDC to `notch-dev.testnet`; memo `notch:claim:<market-id>` | same |
| `paid_total` | `1000000` | `1000000` |
| `unclaimed_reserve` | `0` | `0` |
| Position `claimed_total` | `1000000` | `1000000` |
| Position `claim_state` | `claimed` | `claimed` |
| `get_claimable` after | `0` | `0` |

A deliberate duplicate `claim` on the Trend market was rejected by the contract:

- Transaction: `FEMWzAad5BWYGk8pHQKT87CfMqAUYj2qaoQzNtoMUHu4` — **failed**,
  no token transfer and no state change.
- Post-failure `get_claimable` remained `0` and `claim_state` remained `claimed`.

### Final onchain state

- `market_count`: **2**
- Trend market: `resolved`, `winning_outcome: 0`, totals `["1000000","0"]`,
  escrow `1000000`, paid `1000000`, pending `0`, unclaimed reserve `0`.
- Battle market: `resolved`, `winning_outcome: 0`, totals `["1000000","0"]`,
  escrow `1000000`, paid `1000000`, pending `0`, unclaimed reserve `0`.
- `fee_bps`: `0`.
- Contract configuration unchanged: owner/operator/resolver
  `notch-dev.testnet`; collateral `usdc.tidepool-sandbox.testnet`; minimum entry
  `1000000`; entries not paused.
- No contract redeployment or financial-logic change.

### Caveat: one-sided demonstration

Only the winning side was funded in each market. There was no opposing trader
and no manufactured counterparty. The two claims returned **1 test USDC of
stake each**, restoring the wallet from 98 to 100 test USDC. This proves
collateral recovery, claim accounting and settlement mechanics; it is **not**
trading profit and not a two-party market demonstration.

### Evidence and tests

- `docs/evidence/s2_5_execution_20261112.json` — machine-readable lifecycle
  summary.
- `docs/evidence/s2_5_short_create_args_*.json` — creation payloads.
- `docs/evidence/s2_5_deposit_*.json` — NEP-141 deposit payloads.
- `docs/evidence/s2_5_close_*.json`, `s2_5_resolve_*_args.json`,
  `s2_5_claim_*.json` — lifecycle payloads.
- `docs/evidence/s2_5_resolution_plan_*.json` — oracle plans with onchain
  market snapshots.
- Regression tests: **65 S3B**, **76 S3A**, **109 Rust** passing.
- No private key, seed phrase or signature is stored in the repository.
