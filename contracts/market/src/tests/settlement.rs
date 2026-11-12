//! S1 unit tests: pooled payouts, rounding dust, void refunds, claim
//! idempotency, failed-transfer recovery and conservation.

use near_sdk::json_types::U128;
use near_sdk::mock::MockAction;
use near_sdk::NearToken;

use super::harness::*;

// ---------------------------------------------------------------------------
// Payouts and rounding
// ---------------------------------------------------------------------------

#[test]
fn payout_both_sides_with_rounding_dust() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, CAROL, MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);

    resolve(&mut contract, "m1", 0, T_RESOLVE);
    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.escrow_total, U128(201 * MIN_ENTRY));
    assert_eq!(totals.winning_pool, Some(U128(101 * MIN_ENTRY)));

    // Base-unit arithmetic: floor(100M * 201M / 101M) = 199_009_900 and
    // floor(1M * 201M / 101M) = 1_990_099.
    assert_eq!(claimable(&contract, "m1", ALICE), 199_009_900);
    assert_eq!(claimable(&contract, "m1", CAROL), 1_990_099);
    assert_eq!(claimable(&contract, "m1", BOB), 0);

    assert_eq!(
        claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE),
        199_009_900
    );
    assert_eq!(
        claim_and_settle(&mut contract, CAROL, "m1", true, T_RESOLVE),
        1_990_099
    );

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(200_999_999));
    assert_eq!(totals.pending_total, U128(0));
    // 1 base unit of rounding dust remains locked and is reported, not paid.
    assert_eq!(totals.unclaimed_reserve, U128(1));
    assert_eq!(
        totals.paid_total.0 + totals.unclaimed_reserve.0,
        totals.escrow_total.0
    );

    let alice = position(&contract, "m1", ALICE).unwrap();
    assert_eq!(alice.claimed_total, U128(199_009_900));
    assert_eq!(alice.claim_state, "claimed");
}

#[test]
fn payout_exact_split_has_no_dust() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, CAROL, 200 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 300 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    assert_eq!(claimable(&contract, "m1", ALICE), 200 * MIN_ENTRY);
    assert_eq!(claimable(&contract, "m1", CAROL), 400 * MIN_ENTRY);

    claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE);
    claim_and_settle(&mut contract, CAROL, "m1", true, T_RESOLVE);
    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(600 * MIN_ENTRY));
    assert_eq!(totals.unclaimed_reserve, U128(0));
}

#[test]
fn single_sided_market_returns_each_winning_stake() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 250 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    assert_eq!(claimable(&contract, "m1", ALICE), 100 * MIN_ENTRY);
    assert_eq!(claimable(&contract, "m1", BOB), 250 * MIN_ENTRY);
    claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE);
    claim_and_settle(&mut contract, BOB, "m1", true, T_RESOLVE);

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(350 * MIN_ENTRY));
    assert_eq!(totals.unclaimed_reserve, U128(0));
}

#[test]
fn losing_position_claims_nothing() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    assert_eq!(claimable(&contract, "m1", BOB), 0);
    let bob = position(&contract, "m1", BOB).unwrap();
    assert_eq!(bob.claim_state, "not_eligible");
}

#[test]
#[should_panic(expected = "ERR_NOTHING_TO_CLAIM")]
fn losing_position_claim_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
    claim(&mut contract, BOB, "m1", T_RESOLVE);
}

#[test]
#[should_panic(expected = "ERR_NO_POSITION")]
fn non_participant_claim_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
    claim(&mut contract, CAROL, "m1", T_RESOLVE);
}

#[test]
fn claimable_amounts_never_exceed_pool_for_many_splits() {
    let splits: [(u128, u128, u128); 8] = [
        (1, 1, 1),
        (1, 1, 7),
        (5, 3, 2),
        (9, 1, 10),
        (100, 1, 1),
        (7, 7, 13),
        (1000, 999, 1),
        (13, 5, 8),
    ];

    for (index, (a1, a2, b)) in splits.into_iter().enumerate() {
        let market_id = format!("m{index}");
        let mut contract = init();
        create(&mut contract, &market_id);
        deposit(&mut contract, ALICE, a1 * MIN_ENTRY, &market_id, 0, T_ENTRY);
        deposit(&mut contract, CAROL, a2 * MIN_ENTRY, &market_id, 0, T_ENTRY);
        deposit(&mut contract, BOB, b * MIN_ENTRY, &market_id, 1, T_ENTRY);
        resolve(&mut contract, &market_id, 0, T_RESOLVE);

        let escrow = (a1 + a2 + b) * MIN_ENTRY;
        let payouts =
            claimable(&contract, &market_id, ALICE) + claimable(&contract, &market_id, CAROL);
        let expected_alice = a1 * MIN_ENTRY * escrow / ((a1 + a2) * MIN_ENTRY);
        let expected_carol = a2 * MIN_ENTRY * escrow / ((a1 + a2) * MIN_ENTRY);
        assert_eq!(claimable(&contract, &market_id, ALICE), expected_alice);
        assert_eq!(claimable(&contract, &market_id, CAROL), expected_carol);
        assert_eq!(payouts, expected_alice + expected_carol);
        assert!(
            payouts <= escrow,
            "payouts {payouts} must not exceed escrow {escrow} for {a1}/{a2}/{b}"
        );
    }
}

// ---------------------------------------------------------------------------
// Claim lifecycle and failed transfers
// ---------------------------------------------------------------------------

#[test]
fn payout_is_pending_until_transfer_callback_confirms() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    let amount = claim(&mut contract, ALICE, "m1", T_RESOLVE);
    assert_eq!(amount, 200 * MIN_ENTRY);

    let pending = position(&contract, "m1", ALICE).unwrap();
    assert_eq!(pending.claim_state, "pending");
    assert_eq!(pending.pending_amount, U128(amount));
    assert_eq!(
        pending.claimed_total,
        U128(0),
        "not paid before confirmation"
    );
    assert_eq!(pending.claimable, U128(0));

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(0), "not paid before confirmation");
    assert_eq!(totals.pending_total, U128(amount));
    assert_eq!(totals.unclaimed_reserve, U128(0));

    settle_claim(&mut contract, ALICE, "m1", amount, true, T_RESOLVE);
    let settled = position(&contract, "m1", ALICE).unwrap();
    assert_eq!(settled.claim_state, "claimed");
    assert_eq!(settled.claimed_total, U128(amount));

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(amount));
    assert_eq!(totals.pending_total, U128(0));
}

#[test]
#[should_panic(expected = "ERR_CLAIM_PENDING")]
fn double_claim_while_transfer_is_pending_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    claim(&mut contract, ALICE, "m1", T_RESOLVE);
    claim(&mut contract, ALICE, "m1", T_RESOLVE);
}

#[test]
#[should_panic(expected = "ERR_NOTHING_TO_CLAIM")]
fn double_claim_after_settlement_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE);
    claim(&mut contract, ALICE, "m1", T_RESOLVE + 1);
}

#[test]
fn failed_transfer_restores_claimability_and_retry_succeeds() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    let amount = claim(&mut contract, ALICE, "m1", T_RESOLVE);
    settle_claim(&mut contract, ALICE, "m1", amount, false, T_RESOLVE);

    let after_failure = position(&contract, "m1", ALICE).unwrap();
    assert_eq!(after_failure.claim_state, "claimable");
    assert_eq!(after_failure.pending_amount, U128(0));
    assert_eq!(after_failure.claimed_total, U128(0));
    assert_eq!(after_failure.claimable, U128(amount));

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(0));
    assert_eq!(totals.pending_total, U128(0));
    assert_eq!(totals.unclaimed_reserve, U128(200 * MIN_ENTRY));

    assert_eq!(
        claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE + 1),
        amount
    );
    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(amount));
}

#[test]
#[should_panic(expected = "ERR_MARKET_NOT_SETTLED")]
fn claim_before_resolution_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    claim(&mut contract, ALICE, "m1", T_ENTRY);
}

#[test]
#[should_panic(expected = "ERR_ONLY_SELF")]
fn claim_callback_rejects_external_callers() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);

    set_env(ATTACKER, T_RESOLVE);
    contract.on_claim_transfer("m1".to_string(), acct(ALICE), U128(100 * MIN_ENTRY));
}

#[test]
#[should_panic(expected = "ERR_INCONSISTENT_STATE")]
fn callback_without_pending_transfer_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
    settle_claim(&mut contract, ALICE, "m1", 100 * MIN_ENTRY, true, T_RESOLVE);
}

#[test]
fn claim_schedules_ft_transfer_and_private_callback() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
    let amount = claim(&mut contract, ALICE, "m1", T_RESOLVE);

    let receipts = near_sdk::test_utils::get_created_receipts();
    let mut saw_ft_transfer = false;
    let mut saw_callback = false;

    for receipt in &receipts {
        for action in &receipt.actions {
            if let MockAction::FunctionCallWeight {
                method_name,
                args,
                attached_deposit,
                ..
            } = action
            {
                if method_name == b"ft_transfer" {
                    let parsed: serde_json::Value =
                        serde_json::from_slice(args).expect("ft_transfer args");
                    assert_eq!(receipt.receiver_id, acct(TOKEN));
                    assert_eq!(parsed["receiver_id"], serde_json::json!(ALICE));
                    assert_eq!(parsed["amount"], serde_json::json!(amount.to_string()));
                    assert_eq!(attached_deposit, &NearToken::from_yoctonear(1));
                    saw_ft_transfer = true;
                }
                if method_name == b"on_claim_transfer" {
                    assert_eq!(receipt.receiver_id, acct(CONTRACT));
                    saw_callback = true;
                }
            }
        }
    }

    assert!(saw_ft_transfer, "ft_transfer receipt missing: {receipts:?}");
    assert!(saw_callback, "callback receipt missing: {receipts:?}");
}

// ---------------------------------------------------------------------------
// Void refunds
// ---------------------------------------------------------------------------

#[test]
fn void_refunds_each_stake_exactly_once() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 50 * MIN_ENTRY, "m1", 1, T_ENTRY);
    void(&mut contract, "m1", T_RESOLVE);

    assert_eq!(claimable(&contract, "m1", ALICE), 100 * MIN_ENTRY);
    assert_eq!(claimable(&contract, "m1", BOB), 50 * MIN_ENTRY);

    assert_eq!(
        claim_refund(&mut contract, ALICE, "m1", T_RESOLVE),
        100 * MIN_ENTRY
    );
    settle_claim(&mut contract, ALICE, "m1", 100 * MIN_ENTRY, true, T_RESOLVE);

    // The generic claim path also refunds a voided market.
    assert_eq!(
        claim_and_settle(&mut contract, BOB, "m1", true, T_RESOLVE),
        50 * MIN_ENTRY
    );

    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(150 * MIN_ENTRY));
    assert_eq!(totals.unclaimed_reserve, U128(0));
}

#[test]
#[should_panic(expected = "ERR_NOTHING_TO_CLAIM")]
fn duplicate_void_refund_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    void(&mut contract, "m1", T_RESOLVE);
    claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE);
    claim_refund(&mut contract, ALICE, "m1", T_RESOLVE + 1);
}

#[test]
#[should_panic(expected = "ERR_MARKET_NOT_VOIDED")]
fn claim_refund_on_resolved_market_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
    claim_refund(&mut contract, ALICE, "m1", T_RESOLVE);
}

#[test]
fn no_winner_market_is_voided_and_every_staker_refunded() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 70 * MIN_ENTRY, "m1", 1, T_ENTRY);

    // No stake on the proposed winning side -> the resolver must void.
    // (`resolve_with_empty_winning_side_requires_void` covers the rejection.)
    void(&mut contract, "m1", T_RESOLVE);
    assert_eq!(
        claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE),
        100 * MIN_ENTRY
    );
    assert_eq!(
        claim_and_settle(&mut contract, BOB, "m1", true, T_RESOLVE),
        70 * MIN_ENTRY
    );
    let totals = contract.get_market_totals("m1".to_string()).unwrap();
    assert_eq!(totals.paid_total, U128(170 * MIN_ENTRY));
    assert_eq!(totals.unclaimed_reserve, U128(0));
}

// ---------------------------------------------------------------------------
// Conservation across markets
// ---------------------------------------------------------------------------

#[test]
fn escrow_conservation_across_markets() {
    let mut contract = init();
    let deposits = [
        ("m1", ALICE, 100 * MIN_ENTRY, 0u8),
        ("m1", CAROL, MIN_ENTRY, 0),
        ("m1", BOB, 75 * MIN_ENTRY, 1),
        ("m2", ALICE, 40 * MIN_ENTRY, 1),
        ("m2", BOB, 60 * MIN_ENTRY, 0),
        ("m2", CAROL, 90 * MIN_ENTRY, 1),
    ];

    create(&mut contract, "m1");
    set_env(OPERATOR, T0);
    contract.create_market(market_args("m2", T0, T_CLOSE, T_CLOSE));

    let mut total_deposited = 0u128;
    for (market_id, account, amount, outcome) in deposits {
        assert_eq!(
            deposit(&mut contract, account, amount, market_id, outcome, T_ENTRY),
            0
        );
        total_deposited += amount;
    }

    let mut total_escrow = 0u128;
    for id in ["m1", "m2"] {
        total_escrow += contract
            .get_market_totals(id.to_string())
            .unwrap()
            .escrow_total
            .0;
    }
    assert_eq!(total_escrow, total_deposited);

    resolve(&mut contract, "m1", 0, T_RESOLVE);
    resolve(&mut contract, "m2", 1, T_RESOLVE);

    let mut total_paid = 0u128;
    total_paid += claim_and_settle(&mut contract, ALICE, "m1", true, T_RESOLVE);
    total_paid += claim_and_settle(&mut contract, CAROL, "m1", true, T_RESOLVE);
    total_paid += claim_and_settle(&mut contract, ALICE, "m2", true, T_RESOLVE);
    total_paid += claim_and_settle(&mut contract, CAROL, "m2", true, T_RESOLVE);

    let mut total_reserve = 0u128;
    for id in ["m1", "m2"] {
        let totals = contract.get_market_totals(id.to_string()).unwrap();
        assert!(totals.paid_total.0 <= totals.escrow_total.0);
        assert_eq!(
            totals.paid_total.0 + totals.pending_total.0 + totals.unclaimed_reserve.0,
            totals.escrow_total.0,
            "market {id} accounting must equal its escrow"
        );
        total_reserve += totals.unclaimed_reserve.0;
    }

    assert_eq!(total_paid + total_reserve, total_escrow);
    assert!(
        total_reserve <= 2 * MIN_ENTRY,
        "only rounding dust may remain"
    );
}
