# S2 verification evidence

Milestone: **S2 — Trend Battles + Testnet Readiness**
Date: 11 November 2026

> **Post-S2 deployment update (2026-11-11 UTC):** The S2 contract is now
> deployed to NEAR testnet at `market.notch-dev.testnet`, with Tidepool USDC
> registered as collateral. Deployment, configuration and wallet evidence are
> in [`docs/TESTNET_DEPLOYMENT.md`](TESTNET_DEPLOYMENT.md). The testnet status
> section below is the historical pre-deployment record.

Status:

- **A. S2 implementation complete and verified locally: YES**
- **B. S2 publicly deployed and verified on NEAR testnet: NO — blocked by
  missing testnet credentials/funding.** No deployment evidence was fabricated.

## 1. Implemented functionality

Trend Battle mode is enabled on the same contract and accounting engine as
Trend Trading.

| Capability | Implementation |
| --- | --- |
| Battle creation | `create_market` accepts `mode = "trend_battle"` with required `battle` config |
| Topic A/B metadata | `BattleTopic { topic_id, source_id, project, article_title, metric }` |
| Shared observation window | Single immutable `observation_start < observation_end <= resolve_after` |
| Frozen comparison formula | `BattleFormula::GrowthComparisonV1` (`growth_comparison_v1`) |
| Minimum baseline rule | `min_baseline_views > 0`, frozen and exposed in views |
| Tie tolerance | `tie_tolerance_bps <= 10000`, frozen and exposed in views |
| Tie policy | `TiePolicy::Void`, frozen and validated |
| Frozen rule hash | Existing `sha256:<64 hex>` market-level requirement |
| Winner resolution | Existing resolver-only `resolve_market`; outcome 0 = Topic A, 1 = Topic B |
| Tie settlement | New resolver-only `resolve_tie`; no winner; `status = voided`, refund path |
| Immutable final states | Resolved cannot be voided; tied/voided cannot be resolved; tie evidence idempotent |
| Shared accounting | Battle entries use the unchanged `ft_on_transfer`, escrow, positions, payout, claim and refund code |

No accounting functions were duplicated. The mode-specific surface is creation
validation and `resolve_tie`.

S2 also adds `resolution_kind` (`winning_outcome | void | tie`) to market views
and `battle` configuration to `MarketView` for clients and evidence pages.

## 2. Files created/changed

| File | Change |
| --- | --- |
| `contracts/market/src/types.rs` | Battle types, tie/resolution enums, stored fields, views |
| `contracts/market/src/lib.rs` | Battle validation, creation branch, `resolve_tie`, view fields |
| `contracts/market/src/tests/harness.rs` | Battle fixtures |
| `contracts/market/src/tests/battle.rs` | **25 new S2 unit tests** |
| `contracts/market/src/tests/entry.rs` | S1 gate test updated to assert S2 battle creation is enabled |
| `contracts/market/src/tests/mod.rs` | Registers the battle test module |
| `contracts/market/res/notch_market.wasm` | Rebuilt S2 artifact |
| `contracts/market/README.md` | S2 interface, collateral, deployment and S3 documentation |
| `tests/integration/tests/market_flow.rs` | Battle helper + `trend_battle_flow` sandbox test |
| `docs/s2_collateral_check.txt` | Raw read-only collateral evidence |
| `docs/S2_VERIFICATION.md` | This report |
| `README.md` | S2 status table and artifact update |

Unchanged: all pre-existing product/PRD/messaging documents, `docs/S1_VERIFICATION.md`,
the S1 test token, and every Trend Trading accounting path. No frontend exists or
was modified.

One S1 test was intentionally adapted:
`trend_battle_creation_is_disabled_in_s1` asserted the S1 gate. S2's acceptance
criteria require that gate to be lifted, so it now asserts validated battle
creation is enabled. The other 83 S1 tests are unchanged and passing.

## 3. Tests and build results

Environment: Windows 11 + Git Bash, Rust 1.96.0, near-sdk 5.30.1; Linux x86_64
via WSL2 Ubuntu for the sandbox.

### Unit tests

```text
$ AWS_LC_SYS_PREBUILT_NASM=1 cargo test -p notch-market      # Windows
running 109 tests
test result: ok. 109 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

$ cargo test -p notch-market                                 # Linux / WSL
running 109 tests
test result: ok. 109 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

Breakdown: 84 S1-derived tests (one updated for S2), 25 new battle tests.

New S2 coverage:

| Required case | Tests |
| --- | --- |
| Valid battle creation + immutable config | `battle_market_creation_records_immutable_configuration` |
| Shared engine entry path | `battle_entries_use_the_shared_s1_engine` |
| Invalid topic/source configuration | `battle_creation_validation_matrix` (17 cases: missing config, duplicate topics, incompatible source/project/metric, source mismatch, invalid window, observation after resolve, zero baseline, excessive tolerance, invalid topic/source/project/title/metric, battle config on Trend Trading) |
| Malformed JSON / invalid enums / missing fields | `battle_json_schema_rejects_invalid_values_and_missing_fields` |
| Both possible winners | `battle_topic_a_winning_side_is_claimable`, `battle_topic_b_winning_side_is_claimable` |
| Tie → VOID → refunds | `battle_tie_voids_and_refunds_every_stake`, `battle_tie_entry_after_tie_is_refunded` |
| Tie idempotency / conflicting tie | `battle_tie_is_idempotent_for_identical_evidence`, `battle_tie_with_different_evidence_rejected` |
| No retroactive winner / no tie after resolve | `winner_resolution_after_tie_rejected`, `tie_after_winner_resolution_rejected`, `tie_after_manual_void_rejected` |
| Tie authorization / time / evidence / mode | `tie_resolution_requires_resolver`, `tie_resolution_before_resolve_after_rejected`, `tie_resolution_invalid_evidence_rejected`, `tie_resolution_rejected_for_trend_trading` |
| No winning positions | `battle_resolution_with_empty_winning_side_rejected` |
| Duplicate resolution | `battle_resolution_is_idempotent_and_conflicts_rejected` |
| Duplicate claims | `battle_duplicate_claim_rejected` |
| Cross-mode conservation | `cross_mode_accounting_conservation` |
| Failed FT transfer recovery | `battle_failed_transfer_restores_claimability` (plus existing S1 recovery test) |
| Manual void refunds for battles | `battle_manual_void_still_supports_refunds` |
| Stable view serialization | `battle_view_serializes_stable_strings`, `battle_resolution_kind_is_exposed_for_manual_void` |

### Sandbox integration tests

```text
$ cd tests/integration && cargo test --test market_flow -- --nocapture
running 3 tests
test trend_trading_end_to_end ... ok
test void_refund_and_failed_transfer_recovery ... ok
test trend_battle_flow ... ok

test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

`trend_battle_flow` verifies on a real near-sandbox with a real NEP-141 token:

- battle creation and both-side `ft_transfer_call` entries;
- close → Topic B winner resolution → exact payout to the winning side;
- contract token balance reaches zero and duplicate claim fails;
- a second battle resolves as a tie via `resolve_tie`;
- both sides receive exact refunds through `claim_refund` / `claim`;
- identical tie evidence is idempotent; conflicting evidence and a retroactive
  winning outcome both fail.

### Build and lint

```text
$ cargo fmt --check
(clean)

$ AWS_LC_SYS_PREBUILT_NASM=1 cargo clippy -p notch-market --all-targets
Finished `dev` profile [unoptimized + debuginfo] target(s)
(no warnings or errors)

$ cargo build --release --target wasm32-unknown-unknown -p notch-market
Finished `release` profile [optimized] target(s)

size:   451,574 bytes
sha256: 9892eaa0c113378ca188137d6565d444ff6a8794bda3a596ce1fdcbb692f0f08
```

The artifact was rebuilt from touched sources and reproduced the same hash.

## 4. Collateral token compatibility

Source of truth: live `GET https://www.usetidepool.tech/v0/tokens` and NEAR
testnet RPC. Raw output: `docs/s2_collateral_check.txt`.

| Check | Result |
| --- | --- |
| Tidepool supported NEAR USDC | `usdc.tidepool-sandbox.testnet` |
| Token list metadata | `assetId: nep141:usdc.tidepool-sandbox.testnet`, decimals **6**, symbol `USDC` |
| Account exists | Yes (block ~277,276,390); code hash `DgV3WsKJsGtCjNWxYzFvi599szo7oojkKXWCoGBBAHwj` |
| `ft_metadata` | `ft-1.0.0`, `Tidepool Testnet USDC (no value)`, 6 decimals |
| Total supply at check | `2005900000000` base units = 2,005,900 USDC |
| NEP-141 transfer methods | `ft_transfer`, `ft_transfer_call` present (read-only probe panics on missing 1 yoctoNEAR) |
| `ft_resolve_transfer` | Present |
| Storage registration | `storage_deposit` present; bounds min = max = `1250000000000000000000` yocto = **0.00125 NEAR** |
| Intended market account | `notch-market.testnet` does **not exist**; `storage_balance_of` = `null` |
| Live deposit into Notch | **Not performed** — no signer/funding |

Conclusion: the token is a compatible NEP-141 with 6 decimals and known storage
requirements, and the final market account must call `storage_deposit` (or have
it called on its behalf) before receiving deposits. The local test token is
**not** the Tidepool token; they merely share 6 decimals. A live end-to-end
transfer with Tidepool USDC remains unverified until deployment.

Tidepool is a community sandbox, not official NEAR Intents. Test tokens have no
value. Faucet: <https://app.usetidepool.tech/faucet> (100 test USDC+USDT per
claim, one claim per address every 7 days).

## 5. Testnet deployment status

**Pending. No public deployment was performed.**

Checked on 2026-11-11:

- `near` CLI: not installed on Windows or WSL.
- `~/.near-credentials`: absent on Windows and WSL.
- `NEAR_*` / `TIDEPOOL*` signing environment variables: absent.
- `notch-market.testnet`: `UNKNOWN_ACCOUNT` on testnet.
- Current tooling: `near-cli-rs` **0.31.1** (crates.io and npm); the legacy
  `near-cli` JS package is 4.0.13 and is not the recommended path.

No account was created, no key was generated, no wasm was deployed, and no
transaction hash exists to report. A disposable staging deployment using the
local test token was also not possible for the same reason.

Manual deployment steps, including the Tidepool `storage_deposit` registration
and `min_entry_amount` in 6-decimal base units, are in
`contracts/market/README.md` section 14. After execution, this document must be
updated with:

- market account ID and creation transaction;
- deployed wasm hash and deployment transaction;
- `get_contract_config` output;
- token `storage_balance_of(market)` result;
- a real `ft_transfer_call` deposit transaction;
- resolution/tie transaction and claim transaction;
- explorer links and final balances.

## 6. Remaining risks

1. **Resolver trust for tie tolerance:** the contract stores the tolerance and
   enforces a VOID/refund path, but it cannot verify external pageview values.
   A resolver could still choose a winner incorrectly. S3's oracle/evidence
   pipeline is required to reduce this trust.
2. **Evidence is a commitment, not truth:** `evidence_hash` is tamper evidence
   for external data, not proof the source is organic or correct.
3. **No live Tidepool deposit:** interface/metadata/storage compatibility is
   verified, but a real deposit and payout with Tidepool USDC have not run.
4. **Deployment unavailable:** credentials/funding are missing; final account
   and token registration remain pending.
5. **Callback out-of-gas liveness:** a successful FT transfer with an
   under-funded callback could leave a pending claim. No escrow-moving admin
   override exists; documented as a later security fix.
6. **Dust is locked:** rounding remainders are reported but not sweepable.
7. **S2 is not state-compatible with S1:** deploy fresh; there is no migration.
8. **Storage costs** are paid by the contract account, not users.

## 7. Exact S3 prerequisites

1. Complete the testnet deployment above with Tidepool USDC and register the
   market account with the token.
2. Freeze and publish the battle rule documents whose hashes are used as
   `rule_hash`.
3. Build the Wikimedia pageviews snapshotter:
   - identified User-Agent, rate-limit compliance, caching;
   - full reporting-day windows, baseline and target observations for both
     topics;
   - canonical JSON, SHA-256 digest, raw payload retention;
   - minimum-baseline and missing-data checks.
4. Implement the deterministic `growth_comparison_v1` calculator:
   - topic growth for A and B over the shared window;
   - absolute difference in basis points;
   - tie when `difference <= tie_tolerance_bps`;
   - exact same inputs must reproduce the same digest and outcome.
5. Add the authorized resolver worker:
   - freshness and source-health gates;
   - idempotent job state;
   - calls `resolve_market` for a winner or `resolve_tie` for a tie;
   - never resolves without a committed evidence digest.
6. Expose evidence verification (server/API or proof page) linking the onchain
   `evidence_hash` to the canonical JSON and source URLs.
7. Re-run the S2 unit + sandbox suites and add oracle fixture tests:
   threshold equality, negative growth, baseline below minimum, missing data,
   tie tolerance boundary, and replay determinism.

Until those exist, S2's resolver remains a manual trusted actor and the
deployment remains testnet-only.
