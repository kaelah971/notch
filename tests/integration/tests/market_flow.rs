//! Real-chain (near-sandbox) integration tests for the Notch market contract.
//!
//! Required artifacts:
//! - `contracts/market/res/notch_market.wasm`
//! - `tests/test-token/target/wasm32-unknown-unknown/release/notch_test_token.wasm`
//!
//! Run from `tests/integration`:
//! ```text
//! cargo test --test market_flow -- --nocapture
//! ```
//! near-workspaces supports linux-x86_64, linux-aarch64 and darwin-arm64. On
//! Windows run the suite inside WSL (Ubuntu) as documented in the README.

use anyhow::{bail, Result};
use near_workspaces::network::Sandbox;
use near_workspaces::result::ExecutionFinalResult;
use near_workspaces::types::{Gas, NearToken};
use near_workspaces::{Account, Contract, Worker};
use serde_json::{json, Value};
use std::time::Duration;

const MARKET_WASM: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../contracts/market/res/notch_market.wasm"
);
const TOKEN_WASM: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../test-token/target/wasm32-unknown-unknown/release/notch_test_token.wasm"
);

const MIN_ENTRY: u128 = 1_000_000;
const NANOS_PER_DAY: u64 = 86_400_000_000_000;
const HOUR_NS: u64 = 3_600_000_000_000;

fn digest(ch: char) -> String {
    format!("sha256:{}", ch.to_string().repeat(64))
}

fn ok(result: ExecutionFinalResult) -> Result<()> {
    if result.is_success() {
        Ok(())
    } else {
        bail!("transaction failed: {:#?}", result.failures())
    }
}

async fn view(market: &Contract, method: &str, args: Value) -> Result<Value> {
    Ok(market.view(method).args_json(args).await?.json()?)
}

async fn balance(token: &Contract, account_id: &str) -> Result<u128> {
    let value: Value = token
        .view("ft_balance_of")
        .args_json(json!({ "account_id": account_id }))
        .await?
        .json()?;
    Ok(value
        .as_str()
        .expect("U128 serializes as a string")
        .parse()?)
}

async fn register(token: &Contract, payer: &Account, target: &Account) -> Result<()> {
    ok(payer
        .call(token.id(), "storage_deposit")
        .args_json(json!({
            "account_id": target.id(),
            "registration_only": true,
        }))
        .deposit(NearToken::from_near(1))
        .transact()
        .await?)
}

async fn transfer(token: &Contract, owner: &Account, to: &Account, amount: u128) -> Result<()> {
    ok(owner
        .call(token.id(), "ft_transfer")
        .args_json(json!({
            "receiver_id": to.id(),
            "amount": amount.to_string(),
        }))
        .deposit(NearToken::from_yoctonear(1))
        .transact()
        .await?)
}

/// Calls `ft_transfer_call` into the market. A receiver-side rejection is a
/// successful token transaction whose unused amount is refunded.
async fn enter(
    token: &Contract,
    account: &Account,
    market: &Contract,
    market_id: &str,
    outcome: u8,
    amount: u128,
) -> Result<u128> {
    let balance_before = balance(token, account.id().as_str()).await?;
    let msg = json!({ "market_id": market_id, "outcome": outcome }).to_string();

    let result = account
        .call(token.id(), "ft_transfer_call")
        .args_json(json!({
            "receiver_id": market.id(),
            "amount": amount.to_string(),
            "msg": msg,
        }))
        .deposit(NearToken::from_yoctonear(1))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?;
    if result.failures().len() > 0 {
        bail!("ft_transfer_call had failures: {:#?}", result.failures());
    }

    let balance_after = balance(token, account.id().as_str()).await?;
    Ok(balance_before - balance_after)
}

async fn advance_past(worker: &Worker<Sandbox>, target: u64) -> Result<()> {
    for _ in 0..40 {
        if worker.view_block().await?.timestamp() >= target {
            return Ok(());
        }
        worker.fast_forward(2).await?;
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    bail!("sandbox clock did not advance past {target}");
}

struct Fixture {
    worker: Worker<Sandbox>,
    token: Contract,
    token2: Contract,
    market: Contract,
    owner: Account,
    operator: Account,
    resolver: Account,
    alice: Account,
    bob: Account,
}

async fn fixture() -> Result<Fixture> {
    let market_wasm = std::fs::read(MARKET_WASM)
        .unwrap_or_else(|err| panic!("cannot read {MARKET_WASM}: {err}; build the contract first"));
    let token_wasm = std::fs::read(TOKEN_WASM).unwrap_or_else(|err| {
        panic!("cannot read {TOKEN_WASM}: {err}; build the test token first")
    });

    let worker = near_workspaces::sandbox().await?;
    let owner = worker.dev_create_account().await?;
    let operator = worker.dev_create_account().await?;
    let resolver = worker.dev_create_account().await?;
    let alice = worker.dev_create_account().await?;
    let bob = worker.dev_create_account().await?;
    let token_owner = worker.dev_create_account().await?;

    let token = worker.dev_deploy(&token_wasm).await?;
    ok(token
        .call("new")
        .args_json(json!({
            "owner_id": token_owner.id(),
            "total_supply": "1000000000000",
        }))
        .transact()
        .await?)?;

    let token2 = worker.dev_deploy(&token_wasm).await?;
    ok(token2
        .call("new")
        .args_json(json!({
            "owner_id": token_owner.id(),
            "total_supply": "1000000000000",
        }))
        .transact()
        .await?)?;

    let market = worker.dev_deploy(&market_wasm).await?;
    ok(market
        .call("new")
        .args_json(json!({
            "owner": owner.id(),
            "operator": operator.id(),
            "resolver": resolver.id(),
            "collateral_token": token.id(),
            "min_entry_amount": MIN_ENTRY.to_string(),
        }))
        .transact()
        .await?)?;

    register(&token, &token_owner, &alice).await?;
    register(&token, &token_owner, &bob).await?;
    register(&token, &token_owner, market.as_account()).await?;
    register(&token2, &token_owner, &alice).await?;
    register(&token2, &token_owner, market.as_account()).await?;

    transfer(&token, &token_owner, &alice, 1_000 * MIN_ENTRY).await?;
    transfer(&token, &token_owner, &bob, 1_000 * MIN_ENTRY).await?;
    transfer(&token2, &token_owner, &alice, 100 * MIN_ENTRY).await?;

    Ok(Fixture {
        worker,
        token,
        token2,
        market,
        owner,
        operator,
        resolver,
        alice,
        bob,
    })
}

async fn create_market(
    fixture: &Fixture,
    market_id: &str,
    close_at: u64,
    resolve_after: u64,
) -> Result<()> {
    let now = fixture.worker.view_block().await?.timestamp();
    ok(fixture
        .operator
        .call(fixture.market.id(), "create_market")
        .args_json(json!({
            "args": {
                "market_id": market_id,
                "mode": "trend_trading",
                "question": "Will daily article views for Topic X grow by at least 15%?",
                "choices": ["UP", "DOWN"],
                "source_id": "wikimedia-pageviews-v1",
                "rule_hash": digest('a'),
                "open_at": now.to_string(),
                "close_at": close_at.to_string(),
                "resolve_after": resolve_after.to_string(),
                "invalidation_policy": "refund_on_void",
            }
        }))
        .transact()
        .await?)
}

async fn create_battle_market(
    fixture: &Fixture,
    market_id: &str,
    close_at: u64,
    resolve_after: u64,
) -> Result<()> {
    let now = fixture.worker.view_block().await?.timestamp();
    ok(fixture
        .operator
        .call(fixture.market.id(), "create_market")
        .args_json(json!({
            "args": {
                "market_id": market_id,
                "mode": "trend_battle",
                "question": "Which topic grows faster: AI Agents or Gaming?",
                "choices": ["AI Agents", "Gaming"],
                "source_id": "wikimedia-pageviews-v1",
                "rule_hash": digest('f'),
                "open_at": now.to_string(),
                "close_at": close_at.to_string(),
                "resolve_after": resolve_after.to_string(),
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
                    "observation_start": (now - 2 * NANOS_PER_DAY).to_string(),
                    "observation_end": (now - NANOS_PER_DAY).to_string(),
                    "formula": "growth_comparison_v1",
                    "min_baseline_views": "1000",
                    "tie_tolerance_bps": 50,
                    "tie_policy": "void"
                }
            }
        }))
        .transact()
        .await?)
}

#[tokio::test]
async fn trend_trading_end_to_end() -> Result<()> {
    let f = fixture().await?;
    let now = f.worker.view_block().await?.timestamp();
    let close_at = now + 5_000_000_000;
    create_market(&f, "wb-trend", close_at, close_at).await?;

    // A valid NEP-141 transfer-and-call records the position and moves escrow.
    assert_eq!(
        enter(
            &f.token,
            &f.alice,
            &f.market,
            "wb-trend",
            0,
            100 * MIN_ENTRY
        )
        .await?,
        100 * MIN_ENTRY
    );
    assert_eq!(
        enter(&f.token, &f.alice, &f.market, "wb-trend", 0, 10 * MIN_ENTRY).await?,
        10 * MIN_ENTRY
    );
    assert_eq!(
        enter(&f.token, &f.bob, &f.market, "wb-trend", 1, 50 * MIN_ENTRY).await?,
        50 * MIN_ENTRY
    );

    let totals = view(
        &f.market,
        "get_market_totals",
        json!({"market_id": "wb-trend"}),
    )
    .await?;
    assert_eq!(totals["escrow_total"], "160000000");
    assert_eq!(totals["totals"][0], "110000000");
    assert_eq!(totals["totals"][1], "50000000");
    assert_eq!(
        balance(&f.token, f.market.id().as_str()).await?,
        160 * MIN_ENTRY
    );

    // A rejected message is refunded through NEP-141 receiver semantics.
    let alice_before = balance(&f.token, f.alice.id().as_str()).await?;
    assert_eq!(
        enter(
            &f.token,
            &f.alice,
            &f.market,
            "unknown-market",
            0,
            5 * MIN_ENTRY
        )
        .await?,
        0
    );
    assert_eq!(
        balance(&f.token, f.alice.id().as_str()).await?,
        alice_before
    );
    assert_eq!(
        balance(&f.token, f.market.id().as_str()).await?,
        160 * MIN_ENTRY
    );

    // A deposit in the wrong token is refunded and never enters escrow.
    let alice_token2_before = balance(&f.token2, f.alice.id().as_str()).await?;
    assert_eq!(
        enter(&f.token2, &f.alice, &f.market, "wb-trend", 0, 5 * MIN_ENTRY).await?,
        0
    );
    assert_eq!(
        balance(&f.token2, f.alice.id().as_str()).await?,
        alice_token2_before
    );
    assert_eq!(
        balance(&f.token, f.market.id().as_str()).await?,
        160 * MIN_ENTRY
    );

    // Close and resolve through the real role-authorized paths.
    advance_past(&f.worker, close_at).await?;
    ok(f.alice
        .call(f.market.id(), "close_market")
        .args_json(json!({"market_id": "wb-trend"}))
        .transact()
        .await?)?;
    ok(f.resolver
        .call(f.market.id(), "resolve_market")
        .args_json(json!({
            "market_id": "wb-trend",
            "winning_outcome": 0,
            "evidence_hash": digest('b'),
        }))
        .transact()
        .await?)?;

    // UP pool = 110, total = 160 -> floor(110 * 160 / 110) = 160.
    let claimable = view(
        &f.market,
        "get_claimable",
        json!({"market_id": "wb-trend", "account_id": f.alice.id()}),
    )
    .await?;
    assert_eq!(claimable, "160000000");

    let alice_before = balance(&f.token, f.alice.id().as_str()).await?;
    ok(f.alice
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "wb-trend"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?)?;
    assert_eq!(
        balance(&f.token, f.alice.id().as_str()).await?,
        alice_before + 160 * MIN_ENTRY
    );
    assert_eq!(balance(&f.token, f.market.id().as_str()).await?, 0);

    let position = view(
        &f.market,
        "get_position",
        json!({"market_id": "wb-trend", "account_id": f.alice.id()}),
    )
    .await?;
    assert_eq!(position["claim_state"], "claimed");
    assert_eq!(position["claimed_total"], "160000000");

    let totals = view(
        &f.market,
        "get_market_totals",
        json!({"market_id": "wb-trend"}),
    )
    .await?;
    assert_eq!(totals["paid_total"], "160000000");
    assert_eq!(totals["pending_total"], "0");
    assert_eq!(totals["unclaimed_reserve"], "0");

    // A second claim cannot move a single base unit.
    let alice_after = balance(&f.token, f.alice.id().as_str()).await?;
    let duplicate = f
        .alice
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "wb-trend"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?;
    assert!(
        !duplicate.failures().is_empty(),
        "duplicate claim must fail"
    );
    assert_eq!(balance(&f.token, f.alice.id().as_str()).await?, alice_after);

    // Losing side cannot claim.
    let losing = f
        .bob
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "wb-trend"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?;
    assert!(!losing.failures().is_empty(), "losing claim must fail");

    Ok(())
}

#[tokio::test]
async fn void_refund_and_failed_transfer_recovery() -> Result<()> {
    let f = fixture().await?;
    let now = f.worker.view_block().await?.timestamp();

    // ---- Void path -------------------------------------------------------
    create_market(&f, "void-me", now + HOUR_NS, now + HOUR_NS).await?;
    enter(&f.token, &f.alice, &f.market, "void-me", 0, 30 * MIN_ENTRY).await?;
    enter(&f.token, &f.bob, &f.market, "void-me", 1, 20 * MIN_ENTRY).await?;

    ok(f.resolver
        .call(f.market.id(), "void_market")
        .args_json(json!({"market_id": "void-me", "reason_hash": digest('c')}))
        .transact()
        .await?)?;

    let alice_before = balance(&f.token, f.alice.id().as_str()).await?;
    ok(f.alice
        .call(f.market.id(), "claim_refund")
        .args_json(json!({"market_id": "void-me"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?)?;
    assert_eq!(
        balance(&f.token, f.alice.id().as_str()).await?,
        alice_before + 30 * MIN_ENTRY
    );

    let bob_before = balance(&f.token, f.bob.id().as_str()).await?;
    ok(f.bob
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "void-me"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?)?;
    assert_eq!(
        balance(&f.token, f.bob.id().as_str()).await?,
        bob_before + 20 * MIN_ENTRY
    );
    assert_eq!(balance(&f.token, f.market.id().as_str()).await?, 0);

    // ---- Failed FT transfer recovery ------------------------------------
    let close_at = now + 5_000_000_000;
    create_market(&f, "broken-payout", close_at, close_at).await?;
    enter(
        &f.token,
        &f.alice,
        &f.market,
        "broken-payout",
        0,
        10 * MIN_ENTRY,
    )
    .await?;
    enter(
        &f.token,
        &f.bob,
        &f.market,
        "broken-payout",
        1,
        10 * MIN_ENTRY,
    )
    .await?;
    advance_past(&f.worker, close_at).await?;
    ok(f.resolver
        .call(f.market.id(), "resolve_market")
        .args_json(json!({
            "market_id": "broken-payout",
            "winning_outcome": 0,
            "evidence_hash": digest('b'),
        }))
        .transact()
        .await?)?;

    let claimable = view(
        &f.market,
        "get_claimable",
        json!({"market_id": "broken-payout", "account_id": f.alice.id()}),
    )
    .await?;
    assert_eq!(claimable, "20000000");

    // Removing the token contract makes the outgoing ft_transfer fail.
    ok(f.token.delete_contract(f.owner.id()).await?)?;

    let claim_result = f
        .alice
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "broken-payout"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?;
    assert!(
        !claim_result.failures().is_empty(),
        "the FT transfer receipt must fail"
    );

    // The callback must have restored claimability and never marked payment.
    let position = view(
        &f.market,
        "get_position",
        json!({"market_id": "broken-payout", "account_id": f.alice.id()}),
    )
    .await?;
    assert_eq!(position["claim_state"], "claimable");
    assert_eq!(position["pending_amount"], "0");
    assert_eq!(position["claimed_total"], "0");
    assert_eq!(position["claimable"], "20000000");

    let totals = view(
        &f.market,
        "get_market_totals",
        json!({"market_id": "broken-payout"}),
    )
    .await?;
    assert_eq!(totals["paid_total"], "0");
    assert_eq!(totals["pending_total"], "0");
    assert_eq!(totals["escrow_total"], "20000000");
    assert_eq!(totals["unclaimed_reserve"], "20000000");

    Ok(())
}

#[tokio::test]
async fn trend_battle_flow() -> Result<()> {
    let f = fixture().await?;
    let now = f.worker.view_block().await?.timestamp();
    let close_at = now + 5_000_000_000;
    create_battle_market(&f, "battle-ab", close_at, close_at).await?;

    assert_eq!(
        enter(
            &f.token,
            &f.alice,
            &f.market,
            "battle-ab",
            0,
            100 * MIN_ENTRY
        )
        .await?,
        100 * MIN_ENTRY
    );
    assert_eq!(
        enter(&f.token, &f.bob, &f.market, "battle-ab", 1, 100 * MIN_ENTRY).await?,
        100 * MIN_ENTRY
    );

    advance_past(&f.worker, close_at).await?;
    ok(f.resolver
        .call(f.market.id(), "resolve_market")
        .args_json(json!({
            "market_id": "battle-ab",
            "winning_outcome": 1,
            "evidence_hash": digest('b'),
        }))
        .transact()
        .await?)?;

    let market_view = view(&f.market, "get_market", json!({"market_id": "battle-ab"})).await?;
    assert_eq!(market_view["mode"], "trend_battle");
    assert_eq!(market_view["status"], "resolved");
    assert_eq!(market_view["resolution_kind"], "winning_outcome");
    assert_eq!(market_view["winning_choice"], "Gaming");
    assert_eq!(
        view(
            &f.market,
            "get_claimable",
            json!({"market_id": "battle-ab", "account_id": f.bob.id()}),
        )
        .await?,
        "200000000"
    );
    assert_eq!(
        view(
            &f.market,
            "get_claimable",
            json!({"market_id": "battle-ab", "account_id": f.alice.id()}),
        )
        .await?,
        "0"
    );

    let bob_before = balance(&f.token, f.bob.id().as_str()).await?;
    ok(f.bob
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "battle-ab"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?)?;
    assert_eq!(
        balance(&f.token, f.bob.id().as_str()).await?,
        bob_before + 200 * MIN_ENTRY
    );
    assert_eq!(balance(&f.token, f.market.id().as_str()).await?, 0);

    let duplicate = f
        .bob
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "battle-ab"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?;
    assert!(
        !duplicate.failures().is_empty(),
        "duplicate battle claim must fail"
    );

    // ---- Tie -> VOID -> refund ------------------------------------------
    let now = f.worker.view_block().await?.timestamp();
    let tie_close_at = now + 5_000_000_000;
    create_battle_market(&f, "battle-tie", tie_close_at, tie_close_at).await?;
    assert_eq!(
        enter(
            &f.token,
            &f.alice,
            &f.market,
            "battle-tie",
            0,
            50 * MIN_ENTRY
        )
        .await?,
        50 * MIN_ENTRY
    );
    assert_eq!(
        enter(&f.token, &f.bob, &f.market, "battle-tie", 1, 50 * MIN_ENTRY).await?,
        50 * MIN_ENTRY
    );
    advance_past(&f.worker, tie_close_at).await?;

    ok(f.resolver
        .call(f.market.id(), "resolve_tie")
        .args_json(json!({
            "market_id": "battle-tie",
            "evidence_hash": digest('d'),
        }))
        .transact()
        .await?)?;

    let tie_view = view(&f.market, "get_market", json!({"market_id": "battle-tie"})).await?;
    assert_eq!(tie_view["status"], "voided");
    assert_eq!(tie_view["resolution_kind"], "tie");
    assert_eq!(tie_view["winning_outcome"], Value::Null);
    assert_eq!(tie_view["battle"]["tie_policy"], "void");
    assert_eq!(tie_view["battle"]["tie_tolerance_bps"], 50);

    let alice_before = balance(&f.token, f.alice.id().as_str()).await?;
    ok(f.alice
        .call(f.market.id(), "claim_refund")
        .args_json(json!({"market_id": "battle-tie"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?)?;
    assert_eq!(
        balance(&f.token, f.alice.id().as_str()).await?,
        alice_before + 50 * MIN_ENTRY
    );

    let bob_before = balance(&f.token, f.bob.id().as_str()).await?;
    ok(f.bob
        .call(f.market.id(), "claim")
        .args_json(json!({"market_id": "battle-tie"}))
        .gas(Gas::from_tgas(100))
        .transact()
        .await?)?;
    assert_eq!(
        balance(&f.token, f.bob.id().as_str()).await?,
        bob_before + 50 * MIN_ENTRY
    );
    assert_eq!(balance(&f.token, f.market.id().as_str()).await?, 0);

    // Tie finalization is idempotent for identical evidence.
    ok(f.resolver
        .call(f.market.id(), "resolve_tie")
        .args_json(json!({
            "market_id": "battle-tie",
            "evidence_hash": digest('d'),
        }))
        .transact()
        .await?)?;

    // Different tie evidence and a retroactive winner are both rejected.
    let conflicting_tie = f
        .resolver
        .call(f.market.id(), "resolve_tie")
        .args_json(json!({
            "market_id": "battle-tie",
            "evidence_hash": digest('e'),
        }))
        .transact()
        .await?;
    assert!(
        !conflicting_tie.failures().is_empty(),
        "conflicting tie evidence must fail"
    );

    let retroactive_winner = f
        .resolver
        .call(f.market.id(), "resolve_market")
        .args_json(json!({
            "market_id": "battle-tie",
            "winning_outcome": 0,
            "evidence_hash": digest('b'),
        }))
        .transact()
        .await?;
    assert!(
        !retroactive_winner.failures().is_empty(),
        "a tied market cannot be resolved to a winner"
    );

    Ok(())
}
