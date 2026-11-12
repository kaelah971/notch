//! S1 unit tests: close, resolver-authorized resolution, idempotency and void.

use near_sdk::json_types::U128;

use super::harness::*;

// ---------------------------------------------------------------------------
// Closing
// ---------------------------------------------------------------------------

#[test]
#[should_panic(expected = "ERR_ENTRY_WINDOW_OPEN")]
fn close_before_deadline_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    close(&mut contract, "m1", T_CLOSE - 1);
}

#[test]
fn close_at_deadline_is_permissionless_and_idempotent() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);

    let first = close(&mut contract, "m1", T_CLOSE);
    assert_eq!(first.status, "closed");
    assert!(!first.entries_open);

    let second = close(&mut contract, "m1", T_CLOSE + 1);
    assert_eq!(second.status, "closed");
    assert_eq!(second.escrow_total, U128(10 * MIN_ENTRY));
}

#[test]
#[should_panic(expected = "ERR_MARKET_FINALIZED")]
fn close_after_resolution_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
    close(&mut contract, "m1", T_RESOLVE + 1);
}

// ---------------------------------------------------------------------------
// Resolution
// ---------------------------------------------------------------------------

#[test]
#[should_panic(expected = "ERR_NOT_RESOLVER")]
fn operator_cannot_resolve() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    set_env(OPERATOR, T_RESOLVE);
    contract.resolve_market("m1".to_string(), 0, digest('b'));
}

#[test]
#[should_panic(expected = "ERR_NOT_RESOLVER")]
fn owner_cannot_resolve() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    set_env(OWNER, T_RESOLVE);
    contract.resolve_market("m1".to_string(), 0, digest('b'));
}

#[test]
#[should_panic(expected = "ERR_NOT_RESOLVER")]
fn participant_cannot_resolve() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    set_env(ALICE, T_RESOLVE);
    contract.resolve_market("m1".to_string(), 0, digest('b'));
}

#[test]
#[should_panic(expected = "ERR_RESOLVE_TOO_EARLY")]
fn resolve_before_resolve_after_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 10 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_CLOSE - 1);
}

#[test]
#[should_panic(expected = "ERR_NO_WINNING_STAKE")]
fn resolve_with_empty_winning_side_requires_void() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
}

#[test]
#[should_panic(expected = "ERR_INVALID_OUTCOME")]
fn resolve_with_invalid_outcome_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 2, T_RESOLVE);
}

#[test]
#[should_panic(expected = "ERR_INVALID_EVIDENCE_HASH")]
fn resolve_with_invalid_evidence_hash_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    set_env(RESOLVER, T_RESOLVE);
    contract.resolve_market("m1".to_string(), 0, "sha256:xyz".to_string());
}

#[test]
fn resolver_records_final_outcome_and_evidence() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);

    let view = resolve(&mut contract, "m1", 0, T_RESOLVE);
    assert_eq!(view.status, "resolved");
    assert_eq!(view.winning_outcome, Some(0));
    assert_eq!(view.winning_choice, Some("UP".to_string()));
    assert_eq!(view.evidence_hash, Some(digest('b')));
    assert_eq!(view.resolved_at.map(|t| t.0), Some(T_RESOLVE));
    assert_eq!(view.void_reason_hash, None);
    assert!(!view.entries_open);
    assert_eq!(view.totals, [U128(100 * MIN_ENTRY), U128(100 * MIN_ENTRY)]);

    // Entries after resolution are refunded, never silently accepted.
    assert_eq!(
        deposit(&mut contract, CAROL, 10 * MIN_ENTRY, "m1", 0, T_RESOLVE + 1),
        10 * MIN_ENTRY
    );
    assert!(position(&contract, "m1", CAROL).is_none());
}

#[test]
fn resolution_is_idempotent_for_identical_arguments() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);

    let first = resolve(&mut contract, "m1", 0, T_RESOLVE);
    let second = resolve(&mut contract, "m1", 0, T_RESOLVE + NANOS_PER_MINUTE);

    assert_eq!(first.resolved_at, second.resolved_at);
    assert_eq!(first.evidence_hash, second.evidence_hash);
    assert_eq!(first.status, second.status);
    assert_eq!(second.paid_total, U128(0));
}

#[test]
#[should_panic(expected = "ERR_ALREADY_RESOLVED")]
fn conflicting_outcome_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);

    resolve(&mut contract, "m1", 0, T_RESOLVE);
    resolve(&mut contract, "m1", 1, T_RESOLVE + 1);
}

#[test]
#[should_panic(expected = "ERR_ALREADY_RESOLVED")]
fn conflicting_evidence_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    deposit(&mut contract, BOB, 100 * MIN_ENTRY, "m1", 1, T_ENTRY);

    resolve(&mut contract, "m1", 0, T_RESOLVE);
    set_env(RESOLVER, T_RESOLVE + 1);
    contract.resolve_market("m1".to_string(), 0, digest('d'));
}

#[test]
#[should_panic(expected = "ERR_MARKET_VOIDED")]
fn resolve_after_void_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    void(&mut contract, "m1", T_RESOLVE);
    resolve(&mut contract, "m1", 0, T_RESOLVE + 1);
}

// ---------------------------------------------------------------------------
// Void
// ---------------------------------------------------------------------------

#[test]
#[should_panic(expected = "ERR_NOT_AUTHORIZED")]
fn attacker_cannot_void() {
    let mut contract = init();
    create(&mut contract, "m1");
    set_env(ATTACKER, T_RESOLVE);
    contract.void_market("m1".to_string(), digest('c'));
}

#[test]
#[should_panic(expected = "ERR_INVALID_REASON_HASH")]
fn invalid_void_reason_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    set_env(RESOLVER, T_RESOLVE);
    contract.void_market("m1".to_string(), "nope".to_string());
}

#[test]
fn resolver_or_owner_can_void_and_repeat_is_idempotent() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);

    let first = void(&mut contract, "m1", T_RESOLVE);
    assert_eq!(first.status, "voided");
    assert_eq!(first.void_reason_hash, Some(digest('c')));

    let second = void(&mut contract, "m1", T_RESOLVE + 1);
    assert_eq!(second.voided_at, first.voided_at);

    // Owner is also authorized, but a different reason after void is rejected.
    set_env(OWNER, T_RESOLVE + 2);
    contract.void_market("m1".to_string(), digest('c'));
}

#[test]
#[should_panic(expected = "ERR_ALREADY_VOIDED")]
fn conflicting_void_reason_rejected() {
    let mut contract = init();
    create(&mut contract, "m1");
    void(&mut contract, "m1", T_RESOLVE);
    set_env(RESOLVER, T_RESOLVE + 1);
    contract.void_market("m1".to_string(), digest('e'));
}

#[test]
#[should_panic(expected = "ERR_MARKET_RESOLVED")]
fn resolved_market_cannot_be_voided() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    resolve(&mut contract, "m1", 0, T_RESOLVE);
    void(&mut contract, "m1", T_RESOLVE + 1);
}

#[test]
fn empty_market_can_be_voided_without_refunds() {
    let mut contract = init();
    create(&mut contract, "empty");
    let view = void(&mut contract, "empty", T_RESOLVE);
    assert_eq!(view.status, "voided");
    assert_eq!(view.escrow_total, U128(0));
    assert_eq!(view.unclaimed_reserve, U128(0));
}

#[test]
fn lifecycle_events_are_emitted() {
    let mut contract = init();
    create(&mut contract, "m1");
    deposit(&mut contract, ALICE, 100 * MIN_ENTRY, "m1", 0, T_ENTRY);
    close(&mut contract, "m1", T_CLOSE);
    let logs = near_sdk::test_utils::get_logs();
    assert!(logs
        .iter()
        .any(|log| log.contains("\"event\":\"market_closed\"")));

    resolve(&mut contract, "m1", 0, T_RESOLVE);
    let logs = near_sdk::test_utils::get_logs();
    assert!(logs
        .iter()
        .any(|log| log.contains("\"event\":\"market_resolved\"")));
    assert!(logs
        .iter()
        .any(|log| log.contains("\"winning_choice\":\"UP\"")));
}
