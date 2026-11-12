//! S1 unit tests: initialization, authorization, market creation, NEP-141
//! deposits and config/pause controls.

use near_sdk::json_types::U128;
use near_sdk::{env, PromiseOrValue};

use super::harness::*;
use crate::{Contract, MarketMode, MAX_LIST_LIMIT, NUM_OUTCOMES};

// ---------------------------------------------------------------------------
// Initialization and configuration
// ---------------------------------------------------------------------------

#[test]
fn initialize_sets_immutable_config() {
    let contract = init();
    set_env(ALICE, T0);
    let config = contract.get_contract_config();

    assert_eq!(config.owner, acct(OWNER));
    assert_eq!(config.operator, acct(OPERATOR));
    assert_eq!(config.resolver, acct(RESOLVER));
    assert_eq!(config.collateral_token, acct(TOKEN));
    assert_eq!(config.min_entry_amount, U128(MIN_ENTRY));
    assert!(!config.entries_paused);
    assert_eq!(config.market_count, 0);
    assert_eq!(config.fee_bps, 0);
}

#[test]
#[should_panic(expected = "ERR_ALREADY_INITIALIZED")]
fn double_initialization_is_rejected() {
    let contract = init();
    set_env(OWNER, T0);
    // Simulate the state written by the first initialization on chain.
    env::state_write(&contract);
    let _second = Contract::new(
        acct(OWNER),
        acct(OPERATOR),
        acct(RESOLVER),
        acct(TOKEN),
        U128(MIN_ENTRY),
    );
}

#[test]
#[should_panic(expected = "ERR_MIN_ENTRY_ZERO")]
fn initialization_rejects_zero_minimum() {
    set_env(OWNER, T0);
    let _ = Contract::new(
        acct(OWNER),
        acct(OPERATOR),
        acct(RESOLVER),
        acct(TOKEN),
        U128(0),
    );
}

#[test]
fn owner_can_rotate_operator_and_resolver() {
    let mut contract = init();

    set_env(OWNER, T0);
    contract.set_operator(acct("operator2.testnet"));
    contract.set_resolver(acct("resolver2.testnet"));

    let config = contract.get_contract_config();
    assert_eq!(config.operator, acct("operator2.testnet"));
    assert_eq!(config.resolver, acct("resolver2.testnet"));
}

#[test]
#[should_panic(expected = "ERR_NOT_OWNER")]
fn non_owner_cannot_rotate_operator() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    contract.set_operator(acct(ATTACKER));
}

#[test]
#[should_panic(expected = "ERR_NOT_OWNER")]
fn non_owner_cannot_rotate_resolver() {
    let mut contract = init();
    set_env(RESOLVER, T0);
    contract.set_resolver(acct(ATTACKER));
}

#[test]
#[should_panic(expected = "ERR_NOT_AUTHORIZED")]
fn attacker_cannot_pause_entries() {
    let mut contract = init();
    set_env(ATTACKER, T0);
    contract.set_entries_paused(true);
}

#[test]
fn operator_can_pause_and_unpause_entries() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    assert!(contract.set_entries_paused(true));
    assert!(contract.get_contract_config().entries_paused);
    assert!(!contract.set_entries_paused(false));
    assert!(!contract.get_contract_config().entries_paused);
}

// ---------------------------------------------------------------------------
// Market creation
// ---------------------------------------------------------------------------

#[test]
fn operator_creates_trend_trading_market_with_immutable_config() {
    let mut contract = init();
    let view = create(&mut contract, "wb-ai-agents-15pct");

    assert_eq!(view.market_id, "wb-ai-agents-15pct");
    assert_eq!(view.mode, "trend_trading");
    assert_eq!(view.choices, ["UP".to_string(), "DOWN".to_string()]);
    assert_eq!(view.status, "open");
    assert!(view.entries_open);
    assert_eq!(view.totals, [U128(0), U128(0)]);
    assert_eq!(view.escrow_total, U128(0));
    assert_eq!(view.fee_bps, 0);
    assert_eq!(view.rule_hash, digest('a'));
    assert_eq!(view.invalidation_policy, "refund_on_void");
    assert_eq!(view.open_at.0, T0);
    assert_eq!(view.close_at.0, T_CLOSE);
    assert_eq!(view.resolve_after.0, T_CLOSE);
    assert_eq!(view.winning_outcome, None);

    assert_eq!(contract.get_market_count(), 1);
    let listed = contract.list_markets(0, MAX_LIST_LIMIT);
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0].market_id, view.market_id);
}

#[test]
fn market_config_remains_unchanged_after_entries() {
    // S1 exposes no market update method: the struct fields are written once in
    // `create_market` and only lifecycle fields change afterwards.
    let mut contract = init();
    create(&mut contract, "m1");
    set_env(OPERATOR, T_ENTRY);
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    let view = market(&contract, "m1");
    assert_eq!(
        view.question,
        market_args("m1", T0, T_CLOSE, T_CLOSE).question
    );
    assert_eq!(view.rule_hash, digest('a'));
    assert_eq!(view.open_at.0, T0);
}

#[test]
#[should_panic(expected = "ERR_NOT_OPERATOR")]
fn owner_cannot_create_market() {
    let mut contract = init();
    set_env(OWNER, T0);
    contract.create_market(market_args("m1", T0, T_CLOSE, T_CLOSE));
}

#[test]
#[should_panic(expected = "ERR_NOT_OPERATOR")]
fn resolver_cannot_create_market() {
    let mut contract = init();
    set_env(RESOLVER, T0);
    contract.create_market(market_args("m1", T0, T_CLOSE, T_CLOSE));
}

#[test]
fn trend_battle_creation_is_enabled_in_s2() {
    // S1 gated battle creation with ERR_MODE_NOT_ENABLED. S2 lifts that gate
    // and requires validated battle configuration; all S1 accounting tests
    // remain unchanged.
    let mut contract = init();
    set_env(OPERATOR, T0);
    let mut args = market_args("battle-1", T0, T_CLOSE, T_CLOSE);
    args.mode = MarketMode::TrendBattle;
    args.choices = vec!["AI Agents".to_string(), "Gaming".to_string()];
    args.battle = Some(battle_config());
    let view = contract.create_market(args);
    assert_eq!(view.mode, "trend_battle");
    assert!(view.battle.is_some());
}

#[test]
#[should_panic(expected = "ERR_MARKET_EXISTS")]
fn duplicate_market_id_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    set_env(OPERATOR, T_ENTRY);
    contract.create_market(market_args("m1", T_ENTRY, T_CLOSE, T_CLOSE));
}

#[test]
#[should_panic(expected = "ERR_INVALID_MARKET_ID")]
fn invalid_market_id_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    contract.create_market(market_args("bad id with spaces", T0, T_CLOSE, T_CLOSE));
}

#[test]
#[should_panic(expected = "ERR_INVALID_QUESTION")]
fn empty_question_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    let mut args = market_args("m1", T0, T_CLOSE, T_CLOSE);
    args.question = "   ".to_string();
    contract.create_market(args);
}

#[test]
#[should_panic(expected = "ERR_INVALID_CHOICES")]
fn wrong_choice_count_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    let mut args = market_args("m1", T0, T_CLOSE, T_CLOSE);
    args.choices = vec!["UP".to_string()];
    contract.create_market(args);
}

#[test]
#[should_panic(expected = "ERR_INVALID_CHOICES")]
fn identical_choices_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    let mut args = market_args("m1", T0, T_CLOSE, T_CLOSE);
    args.choices = vec!["UP".to_string(), "UP".to_string()];
    contract.create_market(args);
}

#[test]
#[should_panic(expected = "ERR_INVALID_RULE_HASH")]
fn malformed_rule_hash_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    let mut args = market_args("m1", T0, T_CLOSE, T_CLOSE);
    args.rule_hash = "sha256:nothex".to_string();
    contract.create_market(args);
}

#[test]
#[should_panic(expected = "ERR_INVALID_TIME_WINDOW")]
fn empty_time_window_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    contract.create_market(market_args("m1", T0, T0, T0));
}

#[test]
#[should_panic(expected = "ERR_MARKET_ALREADY_CLOSED")]
fn creating_market_that_already_closed_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    contract.create_market(market_args("m1", T0, T0 + 1, T0 + 2));
    // Move the clock past close_at and try a second market with a past close.
    set_env(OPERATOR, T_CLOSE);
    contract.create_market(market_args("m2", T0, T_CLOSE, T_CLOSE));
}

#[test]
#[should_panic(expected = "ERR_INVALID_RESOLVE_TIME")]
fn resolve_time_before_close_rejected() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    contract.create_market(market_args("m1", T0, T_CLOSE, T_CLOSE - 1));
}

#[test]
#[should_panic(expected = "ERR_ENTRIES_PAUSED")]
fn paused_contract_rejects_market_creation() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    contract.set_entries_paused(true);
    contract.create_market(market_args("m1", T0, T_CLOSE, T_CLOSE));
}

// ---------------------------------------------------------------------------
// NEP-141 deposits
// ---------------------------------------------------------------------------

#[test]
fn deposits_record_positions_and_pools() {
    let mut contract = init();
    create(&mut contract, "m1");

    assert_eq!(
        deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY),
        0
    );
    assert_eq!(
        deposit(&mut contract, BOB, 300 * MIN_ENTRY, "m1", 1, T_ENTRY),
        0
    );
    assert_eq!(
        deposit(&mut contract, ALICE, 50 * MIN_ENTRY, "m1", 0, T_ENTRY),
        0
    );

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(
        totals.totals,
        [U128(150 * MIN_ENTRY), U128(300 * MIN_ENTRY)]
    );
    assert_eq!(totals.escrow_total, U128(450 * MIN_ENTRY));
    assert_eq!(totals.paid_total, U128(0));
    assert_eq!(totals.pending_total, U128(0));
    assert_eq!(totals.unclaimed_reserve, U128(450 * MIN_ENTRY));

    let alice = position(&contract, "m1", ALICE).unwrap();
    assert_eq!(alice.stakes, [U128(150 * MIN_ENTRY), U128(0)]);
    assert_eq!(alice.claim_state, "open");
    assert_eq!(alice.claimable, U128(0));

    let bob = position(&contract, "m1", BOB).unwrap();
    assert_eq!(bob.stakes, [U128(0), U128(300 * MIN_ENTRY)]);
}

#[test]
fn wrong_token_deposit_is_refunded() {
    let mut contract = init();
    create(&mut contract, "m1");

    set_env("fake-token.testnet", T_ENTRY);
    let refund =
        match contract.ft_on_transfer(acct(ALICE), U128(100 * MIN_ENTRY), entry_msg("m1", 0)) {
            PromiseOrValue::Value(value) => value.0,
            PromiseOrValue::Promise(_) => panic!("expected refund value"),
        };

    assert_eq!(refund, 100 * MIN_ENTRY);
    assert!(position(&contract, "m1", ALICE).is_none());
    assert_eq!(
        contract
            .get_market_totals("m1".to_string())
            .unwrap()
            .escrow_total,
        U128(0)
    );
}

#[test]
fn malformed_messages_are_refunded() {
    let mut contract = init();
    create(&mut contract, "m1");

    for msg in [
        "".to_string(),
        "{}".to_string(),
        "not json".to_string(),
        r#"{"market_id":"m1"}"#.to_string(),
        r#"{"market_id":"m1","outcome":0,"extra":true}"#.to_string(),
        r#"{"market_id":"m1","outcome":"up"}"#.to_string(),
        format!(
            r#"{{"market_id":"m1","outcome":0,"pad":"{}"}}"#,
            "x".repeat(600)
        ),
    ] {
        set_env(TOKEN, T_ENTRY);
        let refund = match contract.ft_on_transfer(acct(ALICE), U128(10 * MIN_ENTRY), msg) {
            PromiseOrValue::Value(value) => value.0,
            PromiseOrValue::Promise(_) => panic!("expected refund value"),
        };
        assert_eq!(refund, 10 * MIN_ENTRY);
    }

    assert!(position(&contract, "m1", ALICE).is_none());
}

#[test]
fn invalid_amounts_are_refunded() {
    let mut contract = init();
    create(&mut contract, "m1");

    // A zero amount uses the same return value as acceptance (U128(0)); the
    // decisive check is that no position is recorded below.
    assert_eq!(deposit(&mut contract, ALICE, 0, "m1", 0, T_ENTRY), 0);
    assert_eq!(
        deposit(&mut contract, ALICE, MIN_ENTRY - 1, "m1", 0, T_ENTRY),
        MIN_ENTRY - 1
    );
    assert_eq!(
        deposit(
            &mut contract,
            ALICE,
            MIN_ENTRY,
            "m1",
            NUM_OUTCOMES as u8,
            T_ENTRY
        ),
        MIN_ENTRY
    );
    assert_eq!(
        deposit(&mut contract, ALICE, MIN_ENTRY, "m1", 255, T_ENTRY),
        MIN_ENTRY
    );
    assert!(position(&contract, "m1", ALICE).is_none());
}

#[test]
fn unknown_market_deposit_is_refunded() {
    let mut contract = init();
    assert_eq!(
        deposit(
            &mut contract,
            ALICE,
            10 * MIN_ENTRY,
            "does-not-exist",
            0,
            T_ENTRY
        ),
        10 * MIN_ENTRY
    );
}

#[test]
fn entry_window_boundaries() {
    let mut contract = init();
    set_env(OPERATOR, T0);
    let open_at = T0 + NANOS_PER_MINUTE;
    let close_at = T0 + NANOS_PER_HOUR;
    contract.create_market(market_args("m1", open_at, close_at, close_at));

    // Before opening: refunded.
    assert_eq!(
        deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T0),
        10 * MIN_ENTRY
    );
    // Exactly at opening: accepted.
    assert_eq!(
        deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, open_at),
        0
    );
    // One nanosecond before closing: accepted.
    assert_eq!(
        deposit(&mut contract, BOB, 10 * MIN_ENTRY, "m1", 1, close_at - 1),
        0
    );
    // Exactly at closing: refused (half-open window [open_at, close_at)).
    assert_eq!(
        deposit(&mut contract, CAROL, 10 * MIN_ENTRY, "m1", 0, close_at),
        10 * MIN_ENTRY
    );

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.totals, [U128(10 * MIN_ENTRY), U128(10 * MIN_ENTRY)]);
    assert!(position(&contract, "m1", CAROL).is_none());
}

#[test]
fn late_entry_rejected_after_close_transition() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    close(&mut contract, "m1", T_CLOSE);

    assert_eq!(
        deposit(&mut contract, BOB, 10 * MIN_ENTRY, "m1", 1, T_CLOSE),
        10 * MIN_ENTRY
    );
    let view = market(&contract, "m1");
    assert_eq!(view.status, "closed");
    assert!(!view.entries_open);
    assert_eq!(view.escrow_total, U128(10 * MIN_ENTRY));
}

#[test]
fn pause_blocks_entries_but_not_views() {
    let mut contract = init();
    create(&mut contract, "m1");
    set_env(OPERATOR, T_ENTRY);
    contract.set_entries_paused(true);

    assert_eq!(
        deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY),
        10 * MIN_ENTRY
    );
    let view = market(&contract, "m1");
    assert!(view.entries_paused);
    assert!(!view.entries_open);

    set_env(OWNER, T_ENTRY);
    contract.set_entries_paused(false);
    assert_eq!(
        deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY),
        0
    );
}

#[test]
fn paused_contract_still_accepts_claims_and_refunds() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    set_env(OWNER, T_RESOLVE);
    contract.set_entries_paused(true);
    assert_eq!(
        claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE),
        100 * MIN_ENTRY,
        "single-sided winning market returns the stake"
    );
    assert_eq!(
        contract
            .get_market_totals("m1".to_string())
            .unwrap()
            .paid_total,
        U128(100 * MIN_ENTRY)
    );
}

#[test]
fn deposit_event_is_emitted() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    let logs = near_sdk::test_utils::get_logs();
    assert!(
        logs.iter()
            .any(|log| log.contains("\"event\":\"position_entered\"")),
        "logs: {logs:?}"
    );
}

#[test]
fn rejected_deposit_emits_refund_event() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, MIN_ENTRY - 1, "m1", 0, T_ENTRY);
    let logs = near_sdk::test_utils::get_logs();
    assert!(
        logs.iter()
            .any(|log| log.contains("\"event\":\"entry_rejected\"")
                && log.contains("amount_below_minimum")),
        "logs: {logs:?}"
    );
}

#[test]
fn market_view_uses_string_encoded_timestamps_and_amounts() {
    let mut contract = init();
    create(&mut contract, "m1");
    set_env(ALICE, T_ENTRY);
    let view = contract.get_market("m1".to_string()).unwrap();
    let json = serde_json::to_value(&view).unwrap();

    assert_eq!(json["open_at"], serde_json::json!(T0.to_string()));
    assert_eq!(json["close_at"], serde_json::json!(T_CLOSE.to_string()));
    assert_eq!(json["totals"][0], serde_json::json!("0"));
    assert_eq!(json["fee_bps"], serde_json::json!(0));
    assert_eq!(json["mode"], serde_json::json!("trend_trading"));
}
