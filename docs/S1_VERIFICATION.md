# S1 verification evidence

Milestone: **S1 — Near Market Contract Core**
Date: 11 November 2026
Result: **contract and settlement engine verified locally and on a real
near-sandbox; no testnet deployment**

## Environment

| Item | Value |
| --- | --- |
| Host | Windows 11, Git Bash |
| Rust | `rustc 1.96.0 (ac68faa20 2026-05-25)` |
| Cargo | `cargo 1.96.0` |
| Targets | `wasm32-unknown-unknown`, `x86_64-pc-windows-msvc` |
| near-sdk | 5.30.1 |
| Integration sandbox | WSL2 Ubuntu, Linux x86_64 (near-workspaces 0.24.0) |

Windows unit-test note: near-sdk's `unit-testing` feature pulls `aws-lc-sys`,
which wants NASM. Tests were run with `AWS_LC_SYS_PREBUILT_NASM=1`.

Linux path (the CI target) was also executed in WSL2 Ubuntu x86_64: the same 84
unit tests passed without the NASM variable or any Windows-specific workaround.

## Verification commands and observed results

### 1. Formatting

```text
$ cargo fmt --check
(no output; exit 0)
```

### 2. Unit tests

```text
$ AWS_LC_SYS_PREBUILT_NASM=1 cargo test -p notch-market
running 84 tests
test result: ok. 84 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

The suite runs against the real near-sdk mocked runtime (VM context, storage,
receipts, mocked promise results).

### 3. Lints

```text
$ AWS_LC_SYS_PREBUILT_NASM=1 cargo clippy -p notch-market --all-targets
    Finished `dev` profile [unoptimized + debuginfo] target(s)
```

No warnings or errors.

### 4. WASM build

```text
$ cargo build --release --target wasm32-unknown-unknown -p notch-market
    Finished `release` profile [optimized] target(s) in 3.87s
```

Artifact copied to `contracts/market/res/notch_market.wasm`:

```text
size:   416,538 bytes
sha256: dd738ddfab88256f2b1079366543d06d03fdd67597dcf78cb5b7d17e13a4179c
```

Reproducible on this toolchain: rebuilding produced the same hash.

### 5. Real-chain integration tests (near-sandbox)

```text
$ cd tests/integration && cargo test --test market_flow -- --nocapture
running 2 tests
test trend_trading_end_to_end ... ok
test void_refund_and_failed_transfer_recovery ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

The suite deploys a real NEP-141 token (`tests/test-token`, built from
`near-contract-standards`) and the compiled market contract, then exercises:

- `ft_transfer_call` into a valid market and escrow/position updates
- rejection refunds for an unknown market (NEP-141 receiver semantics)
- rejection/refund of a deposit in the wrong token
- permissionless close, resolver resolution with an evidence digest
- exact payout balance change and contract balance reaching zero
- duplicate claim and losing-side claim failures with no balance change
- void refunds through both `claim_refund` and `claim`
- recovery after deleting the token contract, making the outgoing
  `ft_transfer` genuinely fail: the callback restores claimability and
  `paid_total` stays `0`

## Requirement coverage matrix

### A. Contract foundation

| Requirement | Evidence |
| --- | --- |
| Secure initialization | `double_initialization_is_rejected`, `initialization_rejects_zero_minimum`, `initialize_sets_immutable_config`; `#[init]` + explicit state guard |
| Operator/resolver roles | `owner_can_rotate_operator_and_resolver`, `non_owner_cannot_rotate_operator`, `non_owner_cannot_rotate_resolver`, `operator_cannot_resolve`, `owner_cannot_resolve`, `participant_cannot_resolve`, `attacker_cannot_pause_entries` |
| Configurable approved NEP-141 token | `wrong_token_deposit_is_refunded`; token immutable after init (no setter) |
| Market identifiers | `invalid_market_id_rejected`, `duplicate_market_id_rejected` |
| Immutable market config after activation | `operator_creates_trend_trading_market_with_immutable_config`, `market_config_remains_unchanged_after_entries`; no update method exists |
| Lifecycle states | `close_*`, `resolve_*`, `void_*`, `resolved_market_cannot_be_voided`, `close_after_resolution_rejected` |
| Time-based entry restrictions | `entry_window_boundaries`, `late_entry_rejected_after_close_transition`, `close_before_deadline_rejected` |
| Pause for new entries | `pause_blocks_entries_but_not_views`, `paused_contract_rejects_market_creation`, `paused_contract_still_accepts_claims_and_refunds`, `operator_can_pause_and_unpause_entries` |
| Unsigned integer base units | `[u128; 2]` totals/stakes; `U128`/`U64` JSON; `handles_product_that_overflows_u128` |

### B. Market creation

`operator_creates_trend_trading_market_with_immutable_config`,
`owner_cannot_create_market`, `resolver_cannot_create_market`,
`wrong_choice_count_rejected`, `identical_choices_rejected`,
`empty_question_rejected`, `malformed_rule_hash_rejected`,
`empty_time_window_rejected`, `creating_market_that_already_closed_rejected`,
`resolve_time_before_close_rejected`, `trend_battle_creation_is_disabled_in_s1`.

### C. Position entry

`deposits_record_positions_and_pools`, `wrong_token_deposit_is_refunded`,
`malformed_messages_are_refunded`, `invalid_amounts_are_refunded`,
`unknown_market_deposit_is_refunded`, `entry_window_boundaries`,
`late_entry_rejected_after_close_transition`, `pause_blocks_entries_but_not_views`,
plus the real `ft_transfer_call` paths in `trend_trading_end_to_end`.

### D. Settlement

`resolver_records_final_outcome_and_evidence`, `resolution_is_idempotent_for_identical_arguments`,
`conflicting_outcome_rejected`, `conflicting_evidence_rejected`,
`resolve_before_resolve_after_rejected`, `resolve_with_invalid_outcome_rejected`,
`resolve_with_invalid_evidence_hash_rejected`,
`resolve_with_empty_winning_side_requires_void`.

### E. Payouts and refunds

`payout_both_sides_with_rounding_dust`, `payout_exact_split_has_no_dust`,
`single_sided_market_returns_each_winning_stake`,
`claimable_amounts_never_exceed_pool_for_many_splits`,
`losing_position_claims_nothing`, `no_winner_market_is_voided_and_every_staker_refunded`,
`empty_market_can_be_voided_without_refunds`, `void_refunds_each_stake_exactly_once`,
`duplicate_void_refund_rejected`, `double_claim_while_transfer_is_pending_rejected`,
`double_claim_after_settlement_rejected`,
`failed_transfer_restores_claimability_and_retry_succeeds`,
`claim_callback_rejects_external_callers`, `claim_refund_on_resolved_market_rejected`,
`payout_is_pending_until_transfer_callback_confirms`,
`claim_schedules_ft_transfer_and_private_callback`.

### F. Read interfaces

`market_view_uses_string_encoded_timestamps_and_amounts` plus every accounting
test exercising `get_market`, `get_position`, `get_market_totals`,
`get_claimable`, `get_contract_config`, `list_markets`.

### G. Tests

84 unit tests + 2 near-workspaces integration tests. Coverage includes all
required categories: authorization, creation validation, deposits, wrong token,
invalid amounts, late entries, closing, resolution, payout math, rounding/dust,
no-winner void, refunds, duplicate claims, failed-transfer recovery and
conservation.

### H. Build and verification

WASM built and hashed; fmt and clippy clean; no secrets; no testnet deployment
attempted because no signer was available.

## Unverified / blocked

1. **Testnet deployment** — no `near` CLI, no testnet key or funded account in
   this environment. No transaction was fabricated. Commands are in
   `contracts/market/README.md`.
2. **Oracle/resolution automation** — intentionally out of scope (S3).
3. **Real token economics** — the local test token is test-only, 6 decimals,
   minted at initialization. No audited or mainnet token was used.
4. **Callback out-of-gas edge case** — if the private callback receipt itself
   ran out of gas after a successful FT transfer, the pending amount could
   remain stuck. Fixed 20 TGas callback budget + 100 TGas caller guidance; no
   admin override exists by design. A bounded recovery mechanism is a candidate
   for a later security slice.

## Exact next recommended backend slice

**S2 — Trend Battle creation on the same engine, then testnet deployment.**

1. Deploy the frozen S1 artifact and test token to testnet, record account IDs,
   deployment tx hash and wasm hash (requires a signer).
2. Lift the single `ERR_MODE_NOT_ENABLED` gate, add battle-specific immutable
   fields (topic A/B source descriptors, tie policy) and creation validation.
   Reuse `Market`, `Position`, `claimable_for` and the claim/refund flow without
   a second accounting path.
3. Add resolution-policy metadata for battles (tie → void) while keeping the
   resolver-authorized, evidence-digest settlement flow.
4. Run the same unit matrix plus a near-workspaces test proving one battle
   market enters, resolves and pays on testnet.
