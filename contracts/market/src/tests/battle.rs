//! S2 unit tests: Trend Battle configuration, resolution, ties and cross-mode
//! reuse of the S1 accounting engine.

use near_sdk::json_types::{U128, U64};

use super::harness::*;
use crate::{CreateMarketArgs, MarketMode, ResolutionKind};

// ---------------------------------------------------------------------------
// Creation and validation
// ---------------------------------------------------------------------------

#[test]
fn battle_market_creation_records_immutable_configuration() {
    let mut contract = init();
    let view = create_battle(&mut contract, "battle-1");

    assert_eq!(view.market_id, "battle-1");
    assert_eq!(view.mode, "trend_battle");
    assert_eq!(view.status, "open");
    assert_eq!(view.resolution_kind, None);
    assert_eq!(
        view.choices,
        ["AI Agents".to_string(), "Gaming".to_string()]
    );
    assert_eq!(view.source_id, "wikimedia-pageviews-v1");
    assert_eq!(view.rule_hash, digest('f'));
    assert_eq!(view.totals, [U128(0), U128(0)]);
    assert_eq!(view.escrow_total, U128(0));
    assert_eq!(view.fee_bps, 0);

    let battle = view.battle.as_ref().expect("battle config must be stored");
    assert_eq!(battle.topic_a.topic_id, "ai-agents");
    assert_eq!(battle.topic_a.article_title, "AI_agent");
    assert_eq!(battle.topic_b.topic_id, "gaming");
    assert_eq!(battle.topic_b.article_title, "Video_game");
    assert_eq!(battle.topic_a.project, "en.wikipedia.org");
    assert_eq!(battle.topic_b.project, "en.wikipedia.org");
    assert_eq!(battle.topic_a.metric, battle.topic_b.metric);
    assert_eq!(battle.observation_start.0, T_OBS_START);
    assert_eq!(battle.observation_end.0, T_OBS_END);
    assert_eq!(battle.formula, "growth_comparison_v1");
    assert_eq!(battle.min_baseline_views, U64(1_000));
    assert_eq!(battle.tie_tolerance_bps, 50);
    assert_eq!(battle.tie_policy, "void");

    assert_eq!(contract.get_market_count(), 1);
}

#[test]
fn battle_entries_use_the_shared_s1_engine() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");

    assert_eq!(
        deposit(
            &mut contract,
            ALICE,
            100 * MIN_ENTRY,
            "battle-1",
            0,
            T_ENTRY
        ),
        0
    );
    assert_eq!(
        deposit(&mut contract, BOB, 300 * MIN_ENTRY, "battle-1", 1, T_ENTRY),
        0
    );

    let totals = contract.get_market_totals("battle-1".to_string()).unwrap();
    assert_eq!(
        totals.totals,
        [U128(100 * MIN_ENTRY), U128(300 * MIN_ENTRY)]
    );
    assert_eq!(totals.escrow_total, U128(400 * MIN_ENTRY));
    assert_eq!(totals.paid_total, U128(0));

    let alice = position(&contract, "battle-1", ALICE).unwrap();
    assert_eq!(alice.stakes, [U128(100 * MIN_ENTRY), U128(0)]);
    let bob = position(&contract, "battle-1", BOB).unwrap();
    assert_eq!(bob.stakes, [U128(0), U128(300 * MIN_ENTRY)]);
}

fn battle_with(mutate: impl FnOnce(&mut CreateMarketArgs)) -> CreateMarketArgs {
    let mut args = battle_args("placeholder", T0, T_CLOSE, T_CLOSE);
    mutate(&mut args);
    args
}

fn panic_text(payload: Box<dyn std::any::Any + Send>) -> String {
    if let Some(text) = payload.downcast_ref::<String>() {
        text.clone()
    } else if let Some(text) = payload.downcast_ref::<&str>() {
        text.to_string()
    } else {
        "unknown panic".to_string()
    }
}

#[test]
fn battle_creation_validation_matrix() {
    let cases: Vec<(CreateMarketArgs, &'static str)> = vec![
        (
            battle_with(|a| a.battle = None),
            "ERR_MISSING_BATTLE_CONFIG",
        ),
        (
            battle_with(|a| a.battle.as_mut().unwrap().topic_b.topic_id = "ai-agents".to_string()),
            "ERR_TOPICS_NOT_DISTINCT",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().topic_b.article_title = "AI_agent".to_string()
            }),
            "ERR_TOPICS_NOT_DISTINCT",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().topic_b.source_id = "other-source-v1".to_string()
            }),
            "ERR_INCOMPATIBLE_TOPICS",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().topic_b.project = "de.wikipedia.org".to_string()
            }),
            "ERR_INCOMPATIBLE_TOPICS",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().topic_b.metric = "different-metric-v1".to_string()
            }),
            "ERR_INCOMPATIBLE_TOPICS",
        ),
        (
            battle_with(|a| a.source_id = "other-source-v1".to_string()),
            "ERR_SOURCE_MISMATCH",
        ),
        (
            battle_with(|a| {
                let battle = a.battle.as_mut().unwrap();
                battle.observation_start = U64(T_OBS_END);
            }),
            "ERR_INVALID_OBSERVATION_WINDOW",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().observation_end = U64(T_CLOSE + 1);
            }),
            "ERR_OBSERVATION_AFTER_RESOLVE",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().min_baseline_views = U64(0);
            }),
            "ERR_INVALID_MIN_BASELINE",
        ),
        (
            battle_with(|a| a.battle.as_mut().unwrap().tie_tolerance_bps = 10_001),
            "ERR_INVALID_TIE_TOLERANCE",
        ),
        (
            battle_with(|a| a.battle.as_mut().unwrap().topic_a.topic_id = "bad topic".to_string()),
            "ERR_INVALID_TOPIC_ID",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().topic_a.source_id = "bad source".to_string()
            }),
            "ERR_INVALID_TOPIC_SOURCE",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().topic_a.project = "en wikipedia".to_string()
            }),
            "ERR_INVALID_PROJECT",
        ),
        (
            battle_with(|a| a.battle.as_mut().unwrap().topic_a.article_title = "   ".to_string()),
            "ERR_INVALID_ARTICLE_TITLE",
        ),
        (
            battle_with(|a| {
                a.battle.as_mut().unwrap().topic_a.metric = "daily pageviews".to_string()
            }),
            "ERR_INVALID_METRIC",
        ),
        (
            {
                let mut args = market_args("placeholder", T0, T_CLOSE, T_CLOSE);
                args.mode = MarketMode::TrendTrading;
                args.battle = Some(battle_config());
                args
            },
            "ERR_UNEXPECTED_BATTLE_CONFIG",
        ),
    ];

    for (index, (mut args, expected)) in cases.into_iter().enumerate() {
        args.market_id = format!("invalid-{index}");
        let mut contract = init();
        set_env(OPERATOR, T0);
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            contract.create_market(args);
        }));
        let payload = result.expect_err("expected battle creation to fail");
        let message = panic_text(payload);
        assert!(
            message.contains(expected),
            "case {index}: expected {expected}, got {message}"
        );
        assert_eq!(
            contract.get_market_count(),
            0,
            "case {index} created a market"
        );
    }
}

#[test]
fn battle_json_schema_rejects_invalid_values_and_missing_fields() {
    let args = battle_args("json", T0, T_CLOSE, T_CLOSE);

    let mut value = serde_json::to_value(&args).unwrap();
    value["battle"]["tie_policy"] = serde_json::json!("refund");
    assert!(serde_json::from_value::<CreateMarketArgs>(value).is_err());

    let mut value = serde_json::to_value(&args).unwrap();
    value["battle"]["formula"] = serde_json::json!("made_up");
    assert!(serde_json::from_value::<CreateMarketArgs>(value).is_err());

    let mut value = serde_json::to_value(&args).unwrap();
    value["battle"]["topic_a"]
        .as_object_mut()
        .unwrap()
        .remove("metric");
    assert!(serde_json::from_value::<CreateMarketArgs>(value).is_err());

    let mut value = serde_json::to_value(&args).unwrap();
    value["battle"]["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<CreateMarketArgs>(value).is_err());

    // Trend Trading remains backwards compatible when `battle` is omitted.
    let mut trend = serde_json::to_value(market_args("trend", T0, T_CLOSE, T_CLOSE)).unwrap();
    trend.as_object_mut().unwrap().remove("battle");
    let parsed: CreateMarketArgs = serde_json::from_value(trend).unwrap();
    assert!(parsed.battle.is_none());
}

// ---------------------------------------------------------------------------
// Winners
// ---------------------------------------------------------------------------

#[test]
fn battle_topic_a_winning_side_is_claimable() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(
        &mut contract,
        ALICE,
        100 * MIN_ENTRY,
        "battle-1",
        0,
        T_ENTRY,
    );
    deposit(&mut contract, BOB, 300 * MIN_ENTRY, "battle-1", 1, T_ENTRY);

    let view = resolve(&mut contract, "battle-1", 0, T_RESOLVE);
    assert_eq!(view.status, "resolved");
    assert_eq!(view.resolution_kind.as_deref(), Some("winning_outcome"));
    assert_eq!(view.winning_outcome, Some(0));
    assert_eq!(view.winning_choice.as_deref(), Some("AI Agents"));
    assert_eq!(view.evidence_hash, Some(digest('b')));

    assert_eq!(claimable(&contract, "battle-1", ALICE), 400 * MIN_ENTRY);
    assert_eq!(claimable(&contract, "battle-1", BOB), 0);

    assert_eq!(
        claim_and_settle(&mut contract, ALICE, "battle-1", true, T_RESOLVE),
        400 * MIN_ENTRY
    );
    let totals = contract.get_market_totals("battle-1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(400 * MIN_ENTRY));
    assert_eq!(totals.unclaimed_reserve, U128(0));
}

#[test]
fn battle_topic_b_winning_side_is_claimable() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(
        &mut contract,
        ALICE,
        100 * MIN_ENTRY,
        "battle-1",
        0,
        T_ENTRY,
    );
    deposit(&mut contract, BOB, 300 * MIN_ENTRY, "battle-1", 1, T_ENTRY);

    let view = resolve(&mut contract, "battle-1", 1, T_RESOLVE);
    assert_eq!(view.winning_outcome, Some(1));
    assert_eq!(view.winning_choice.as_deref(), Some("Gaming"));

    assert_eq!(claimable(&contract, "battle-1", BOB), 400 * MIN_ENTRY);
    assert_eq!(claimable(&contract, "battle-1", ALICE), 0);
    assert_eq!(
        claim_and_settle(&mut contract, BOB, "battle-1", true, T_RESOLVE),
        400 * MIN_ENTRY
    );
}

#[test]
#[should_panic(expected = "ERR_NO_WINNING_STAKE")]
fn battle_resolution_with_empty_winning_side_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "battle-1", 1, T_ENTRY);
    resolve(&mut contract, "battle-1", 0, T_RESOLVE);
}

#[test]
fn battle_resolution_is_idempotent_and_conflicts_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(
        &mut contract,
        ALICE,
        100 * MIN_ENTRY,
        "battle-1",
        0,
        T_ENTRY,
    );
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "battle-1", 1, T_ENTRY);

    let first = resolve(&mut contract, "battle-1", 0, T_RESOLVE);
    let second = resolve(&mut contract, "battle-1", 0, T_RESOLVE + 1);
    assert_eq!(first.resolved_at, second.resolved_at);
    assert_eq!(first.evidence_hash, second.evidence_hash);

    let outcome_conflict = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        set_env(RESOLVER, T_RESOLVE + 2);
        contract.resolve_market("battle-1".to_string(), 1, digest('b'));
    }));
    assert!(outcome_conflict.is_err());

    let evidence_conflict = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        set_env(RESOLVER, T_RESOLVE + 3);
        contract.resolve_market("battle-1".to_string(), 0, digest('e'));
    }));
    assert!(evidence_conflict.is_err());
}

// ---------------------------------------------------------------------------
// Tie -> VOID -> refunds
// ---------------------------------------------------------------------------

#[test]
fn battle_tie_voids_and_refunds_every_stake() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(
        &mut contract,
        ALICE,
        100 * MIN_ENTRY,
        "battle-1",
        0,
        T_ENTRY,
    );
    deposit(&mut contract, BOB, 300 * MIN_ENTRY, "battle-1", 1, T_ENTRY);

    let view = resolve_tie(&mut contract, "battle-1", T_RESOLVE);
    assert_eq!(view.status, "voided");
    assert_eq!(view.resolution_kind.as_deref(), Some("tie"));
    assert_eq!(view.winning_outcome, None);
    assert_eq!(view.winning_choice, None);
    assert_eq!(view.void_reason_hash, None);
    assert_eq!(view.evidence_hash, Some(digest('d')));
    assert_eq!(view.voided_at.map(|t| t.0), Some(T_RESOLVE));

    assert_eq!(claimable(&contract, "battle-1", ALICE), 100 * MIN_ENTRY);
    assert_eq!(claimable(&contract, "battle-1", BOB), 300 * MIN_ENTRY);

    assert_eq!(
        claim_refund(&mut contract, ALICE, "battle-1", T_RESOLVE),
        100 * MIN_ENTRY
    );
    settle_claim(
        &mut contract,
        ALICE,
        "battle-1",
        100 * MIN_ENTRY,
        true,
        T_RESOLVE,
    );
    assert_eq!(
        claim_and_settle(&mut contract, BOB, "battle-1", true, T_RESOLVE),
        300 * MIN_ENTRY
    );

    let totals = contract.get_market_totals("battle-1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(400 * MIN_ENTRY));
    assert_eq!(totals.pending_total, U128(0));
    assert_eq!(totals.unclaimed_reserve, U128(0));
    assert_eq!(
        totals.paid_total.0 + totals.unclaimed_reserve.0,
        totals.escrow_total.0
    );
}

#[test]
fn battle_tie_is_idempotent_for_identical_evidence() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);

    let first = resolve_tie(&mut contract, "battle-1", T_RESOLVE);
    let second = resolve_tie(&mut contract, "battle-1", T_RESOLVE + 1);
    assert_eq!(first.voided_at, second.voided_at);
    assert_eq!(first.evidence_hash, second.evidence_hash);
    assert_eq!(second.paid_total, U128(0));
}

#[test]
#[should_panic(expected = "ERR_ALREADY_VOIDED")]
fn battle_tie_with_different_evidence_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    resolve_tie(&mut contract, "battle-1", T_RESOLVE);

    set_env(RESOLVER, T_RESOLVE + 1);
    contract.resolve_tie("battle-1".to_string(), digest('e'));
}

#[test]
#[should_panic(expected = "ERR_MARKET_VOIDED")]
fn winner_resolution_after_tie_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    resolve_tie(&mut contract, "battle-1", T_RESOLVE);
    resolve(&mut contract, "battle-1", 0, T_RESOLVE + 1);
}

#[test]
#[should_panic(expected = "ERR_MARKET_RESOLVED")]
fn tie_after_winner_resolution_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    resolve(&mut contract, "battle-1", 0, T_RESOLVE);
    resolve_tie(&mut contract, "battle-1", T_RESOLVE + 1);
}

#[test]
#[should_panic(expected = "ERR_ALREADY_VOIDED")]
fn tie_after_manual_void_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    void(&mut contract, "battle-1", T_RESOLVE);
    resolve_tie(&mut contract, "battle-1", T_RESOLVE + 1);
}

#[test]
#[should_panic(expected = "ERR_NOT_BATTLE_MARKET")]
fn tie_resolution_rejected_for_trend_trading() {
    let mut contract = init();
    create(&mut contract, "trend-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "trend-1", 0, T_ENTRY);
    set_env(RESOLVER, T_RESOLVE);
    contract.resolve_tie("trend-1".to_string(), digest('d'));
}

#[test]
#[should_panic(expected = "ERR_RESOLVE_TOO_EARLY")]
fn tie_resolution_before_resolve_after_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    resolve_tie(&mut contract, "battle-1", T_CLOSE - 1);
}

#[test]
#[should_panic(expected = "ERR_INVALID_EVIDENCE_HASH")]
fn tie_resolution_invalid_evidence_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    set_env(RESOLVER, T_RESOLVE);
    contract.resolve_tie("battle-1".to_string(), "bad".to_string());
}

#[test]
#[should_panic(expected = "ERR_NOT_RESOLVER")]
fn tie_resolution_requires_resolver() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    set_env(OPERATOR, T_RESOLVE);
    contract.resolve_tie("battle-1".to_string(), digest('d'));
}

#[test]
fn battle_tie_entry_after_tie_is_refunded() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    resolve_tie(&mut contract, "battle-1", T_RESOLVE);

    assert_eq!(
        deposit(
            &mut contract,
            CAROL,
            10 * MIN_ENTRY,
            "battle-1",
            1,
            T_RESOLVE + 1
        ),
        10 * MIN_ENTRY
    );
    assert!(position(&contract, "battle-1", CAROL).is_none());
}

#[test]
fn battle_manual_void_still_supports_refunds() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 40 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 60 * MIN_ENTRY, "battle-1", 1, T_ENTRY);

    let view = void(&mut contract, "battle-1", T_RESOLVE);
    assert_eq!(view.status, "voided");
    assert_eq!(view.resolution_kind.as_deref(), Some("void"));
    assert_eq!(view.evidence_hash, None);
    assert_eq!(view.void_reason_hash, Some(digest('c')));

    assert_eq!(
        claim_and_settle(&mut contract, ALICE, "battle-1", true, T_RESOLVE),
        40 * MIN_ENTRY
    );
    assert_eq!(
        claim_and_settle(&mut contract, BOB, "battle-1", true, T_RESOLVE),
        60 * MIN_ENTRY
    );
    let totals = contract.get_market_totals("battle-1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(100 * MIN_ENTRY));
    assert_eq!(totals.unclaimed_reserve, U128(0));
}

// ---------------------------------------------------------------------------
// Claim safety and cross-mode conservation
// ---------------------------------------------------------------------------

#[test]
#[should_panic(expected = "ERR_NOTHING_TO_CLAIM")]
fn battle_duplicate_claim_rejected() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(
        &mut contract,
        ALICE,
        100 * MIN_ENTRY,
        "battle-1",
        0,
        T_ENTRY,
    );
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "battle-1", 1, T_ENTRY);
    resolve(&mut contract, "battle-1", 0, T_RESOLVE);
    claim_and_settle(&mut contract, ALICE, "battle-1", true, T_RESOLVE);
    claim(&mut contract, ALICE, "battle-1", T_RESOLVE + 1);
}

#[test]
fn battle_failed_transfer_restores_claimability() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(
        &mut contract,
        ALICE,
        100 * MIN_ENTRY,
        "battle-1",
        0,
        T_ENTRY,
    );
    deposit(&mut contract, BOB, 300 * MIN_ENTRY, "battle-1", 1, T_ENTRY);
    resolve(&mut contract, "battle-1", 0, T_RESOLVE);

    let amount = claim(&mut contract, ALICE, "battle-1", T_RESOLVE);
    assert_eq!(amount, 400 * MIN_ENTRY);
    settle_claim(&mut contract, ALICE, "battle-1", amount, false, T_RESOLVE);

    let after_failure = position(&contract, "battle-1", ALICE).unwrap();
    assert_eq!(after_failure.claim_state, "claimable");
    assert_eq!(after_failure.claimable, U128(amount));
    assert_eq!(after_failure.pending_amount, U128(0));
    assert_eq!(after_failure.claimed_total, U128(0));

    let totals = contract.get_market_totals("battle-1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(0));
    assert_eq!(totals.pending_total, U128(0));
    assert_eq!(totals.unclaimed_reserve, U128(400 * MIN_ENTRY));

    assert_eq!(
        claim_and_settle(&mut contract, ALICE, "battle-1", true, T_RESOLVE + 1),
        amount
    );
    let totals = contract.get_market_totals("battle-1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(amount));
}

#[test]
fn cross_mode_accounting_conservation() {
    let mut contract = init();
    create(&mut contract, "trend-1");
    create_battle(&mut contract, "battle-1");

    // Trend Trading: 100 UP vs 100 DOWN.
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "trend-1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "trend-1", 1, T_ENTRY);
    // Battle: 50 Topic A vs 150 Topic B.
    deposit(&mut contract, ALICE, 50 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 150 * MIN_ENTRY, "battle-1", 1, T_ENTRY);

    let deposited = 400 * MIN_ENTRY;
    assert_eq!(
        contract
            .get_market_totals("trend-1".to_string())
            .unwrap()
            .escrow_total
            .0
            + contract
                .get_market_totals("battle-1".to_string())
                .unwrap()
                .escrow_total
                .0,
        deposited
    );

    resolve(&mut contract, "trend-1", 0, T_RESOLVE);
    resolve(&mut contract, "battle-1", 1, T_RESOLVE);

    let mut paid = 0u128;
    paid += claim_and_settle(&mut contract, ALICE, "trend-1", true, T_RESOLVE);
    paid += claim_and_settle(&mut contract, BOB, "battle-1", true, T_RESOLVE);

    assert_eq!(paid, 400 * MIN_ENTRY);
    for id in ["trend-1", "battle-1"] {
        let totals = contract.get_market_totals(id.to_string()).unwrap();
        assert!(totals.paid_total.0 <= totals.escrow_total.0);
        assert_eq!(
            totals.paid_total.0 + totals.pending_total.0 + totals.unclaimed_reserve.0,
            totals.escrow_total.0,
            "market {id} conservation"
        );
    }
}

#[test]
fn battle_view_serializes_stable_strings() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "battle-1", 0, T_ENTRY);
    resolve_tie(&mut contract, "battle-1", T_RESOLVE);

    let view = market(&contract, "battle-1");
    let json = serde_json::to_value(&view).unwrap();
    assert_eq!(json["mode"], serde_json::json!("trend_battle"));
    assert_eq!(json["resolution_kind"], serde_json::json!("tie"));
    assert_eq!(
        json["battle"]["observation_start"],
        serde_json::json!(T_OBS_START.to_string())
    );
    assert_eq!(
        json["battle"]["observation_end"],
        serde_json::json!(T_OBS_END.to_string())
    );
    assert_eq!(
        json["battle"]["formula"],
        serde_json::json!("growth_comparison_v1")
    );
    assert_eq!(json["battle"]["tie_policy"], serde_json::json!("void"));
    assert_eq!(
        json["battle"]["min_baseline_views"],
        serde_json::json!("1000")
    );
    assert_eq!(json["battle"]["tie_tolerance_bps"], serde_json::json!(50));
}

#[test]
fn battle_resolution_kind_is_exposed_for_manual_void() {
    let mut contract = init();
    create_battle(&mut contract, "battle-1");
    void(&mut contract, "battle-1", T_RESOLVE);
    let view = market(&contract, "battle-1");
    assert_eq!(view.resolution_kind.as_deref(), Some("void"));
    assert_eq!(view.winning_outcome, None);
    assert_eq!(
        view.resolution_kind,
        Some(ResolutionKind::Void.as_str().to_string())
    );
}
