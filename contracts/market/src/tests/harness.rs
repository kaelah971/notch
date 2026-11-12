//! Shared unit-test harness (mocked NEAR VM, no network).

use near_parameters::RuntimeFeesConfig;
use near_sdk::json_types::{U128, U64};
use near_sdk::test_utils::VMContextBuilder;
use near_sdk::{
    test_vm_config, testing_env, AccountId, Gas, NearToken, PromiseOrValue, PromiseResult,
};

use crate::{
    BattleConfigArgs, BattleFormula, BattleTopic, Contract, CreateMarketArgs, InvalidationPolicy,
    MarketMode, MarketView, PositionView, TiePolicy,
};

pub const CONTRACT: &str = "notch-market.testnet";
pub const OWNER: &str = "owner.testnet";
pub const OPERATOR: &str = "operator.testnet";
pub const RESOLVER: &str = "resolver.testnet";
pub const TOKEN: &str = "usdc.testnet";
pub const ALICE: &str = "alice.testnet";
pub const BOB: &str = "bob.testnet";
pub const CAROL: &str = "carol.testnet";
pub const ATTACKER: &str = "attacker.testnet";

pub const NANOS_PER_MINUTE: u64 = 60_000_000_000;
pub const NANOS_PER_HOUR: u64 = 60 * NANOS_PER_MINUTE;
pub const NANOS_PER_DAY: u64 = 24 * NANOS_PER_HOUR;
pub const T0: u64 = 1_760_000_000_000_000_000;
pub const T_OBS_START: u64 = T0 - 2 * NANOS_PER_DAY;
pub const T_OBS_END: u64 = T0 - NANOS_PER_DAY;

pub const T_ENTRY: u64 = T0 + NANOS_PER_MINUTE;
pub const T_CLOSE: u64 = T0 + NANOS_PER_HOUR;
pub const T_RESOLVE: u64 = T_CLOSE + NANOS_PER_MINUTE;

pub const MIN_ENTRY: u128 = 1_000_000;

pub fn acct(value: &str) -> AccountId {
    value.parse().expect("valid account id")
}

pub fn set_env(predecessor: &str, now: u64) {
    set_env_with_results(predecessor, now, vec![]);
}

pub fn set_env_with_results(predecessor: &str, now: u64, results: Vec<PromiseResult>) {
    let context = VMContextBuilder::new()
        .current_account_id(acct(CONTRACT))
        .predecessor_account_id(acct(predecessor))
        .signer_account_id(acct(predecessor))
        .block_timestamp(now)
        .attached_deposit(NearToken::from_yoctonear(0))
        .prepaid_gas(Gas::from_tgas(300))
        .account_balance(NearToken::from_near(10_000))
        .build();
    testing_env!(
        context,
        test_vm_config(),
        RuntimeFeesConfig::test(),
        Default::default(),
        results
    );
}

pub fn init() -> Contract {
    set_env(OWNER, T0);
    Contract::new(
        acct(OWNER),
        acct(OPERATOR),
        acct(RESOLVER),
        acct(TOKEN),
        U128(MIN_ENTRY),
    )
}

/// `sha256:<64 x ch>` helper.
pub fn digest(ch: char) -> String {
    format!("sha256:{}", ch.to_string().repeat(64))
}

pub fn market_args(id: &str, open_at: u64, close_at: u64, resolve_after: u64) -> CreateMarketArgs {
    CreateMarketArgs {
        market_id: id.to_string(),
        mode: MarketMode::TrendTrading,
        question: "Will daily views for Topic X grow by at least 15%?".to_string(),
        choices: vec!["UP".to_string(), "DOWN".to_string()],
        source_id: "wikimedia-pageviews-v1".to_string(),
        rule_hash: digest('a'),
        open_at: U64(open_at),
        close_at: U64(close_at),
        resolve_after: U64(resolve_after),
        invalidation_policy: InvalidationPolicy::RefundOnVoid,
        battle: None,
    }
}

pub fn battle_topic(topic_id: &str, article_title: &str) -> BattleTopic {
    BattleTopic {
        topic_id: topic_id.to_string(),
        source_id: "wikimedia-pageviews-v1".to_string(),
        project: "en.wikipedia.org".to_string(),
        article_title: article_title.to_string(),
        metric: "daily-pageviews-growth-v1".to_string(),
    }
}

pub fn battle_config() -> BattleConfigArgs {
    BattleConfigArgs {
        topic_a: battle_topic("ai-agents", "AI_agent"),
        topic_b: battle_topic("gaming", "Video_game"),
        observation_start: U64(T_OBS_START),
        observation_end: U64(T_OBS_END),
        formula: BattleFormula::GrowthComparisonV1,
        min_baseline_views: U64(1_000),
        tie_tolerance_bps: 50,
        tie_policy: TiePolicy::Void,
    }
}

pub fn battle_args(id: &str, open_at: u64, close_at: u64, resolve_after: u64) -> CreateMarketArgs {
    CreateMarketArgs {
        market_id: id.to_string(),
        mode: MarketMode::TrendBattle,
        question: "Which topic grows faster: AI Agents or Gaming?".to_string(),
        choices: vec!["AI Agents".to_string(), "Gaming".to_string()],
        source_id: "wikimedia-pageviews-v1".to_string(),
        rule_hash: digest('f'),
        open_at: U64(open_at),
        close_at: U64(close_at),
        resolve_after: U64(resolve_after),
        invalidation_policy: InvalidationPolicy::RefundOnVoid,
        battle: Some(battle_config()),
    }
}

pub fn create_battle(contract: &mut Contract, id: &str) -> MarketView {
    set_env(OPERATOR, T0);
    contract.create_market(battle_args(id, T0, T_CLOSE, T_CLOSE))
}

pub fn create(contract: &mut Contract, id: &str) -> MarketView {
    set_env(OPERATOR, T0);
    contract.create_market(market_args(id, T0, T_CLOSE, T_CLOSE))
}

pub fn entry_msg(id: &str, outcome: u8) -> String {
    serde_json::json!({ "market_id": id, "outcome": outcome }).to_string()
}

/// Returns 0 when the deposit was fully accepted, or the refunded amount.
pub fn deposit(
    contract: &mut Contract,
    sender: &str,
    amount: u128,
    id: &str,
    outcome: u8,
    now: u64,
) -> u128 {
    set_env(TOKEN, now);
    match contract.ft_on_transfer(acct(sender), U128(amount), entry_msg(id, outcome)) {
        PromiseOrValue::Value(value) => value.0,
        PromiseOrValue::Promise(_) => panic!("ft_on_transfer must return a value"),
    }
}

pub fn close(contract: &mut Contract, id: &str, now: u64) -> MarketView {
    // Permissionless by design; use a non-operator caller.
    set_env(ATTACKER, now);
    contract.close_market(id.to_string())
}

pub fn resolve(contract: &mut Contract, id: &str, outcome: u8, now: u64) -> MarketView {
    set_env(RESOLVER, now);
    contract.resolve_market(id.to_string(), outcome, digest('b'))
}

pub fn void(contract: &mut Contract, id: &str, now: u64) -> MarketView {
    set_env(RESOLVER, now);
    contract.void_market(id.to_string(), digest('c'))
}

pub fn resolve_tie(contract: &mut Contract, id: &str, now: u64) -> MarketView {
    set_env(RESOLVER, now);
    contract.resolve_tie(id.to_string(), digest('d'))
}

pub fn claimable(contract: &Contract, id: &str, account: &str) -> u128 {
    contract.get_claimable(id.to_string(), acct(account)).0
}

pub fn position(contract: &Contract, id: &str, account: &str) -> Option<PositionView> {
    contract.get_position(id.to_string(), acct(account))
}

pub fn market(contract: &Contract, id: &str) -> MarketView {
    contract
        .get_market(id.to_string())
        .expect("market should exist")
}

/// Starts a claim and returns the requested amount.
pub fn claim(contract: &mut Contract, account: &str, id: &str, now: u64) -> u128 {
    set_env(account, now);
    let amount = contract.get_claimable(id.to_string(), acct(account)).0;
    let _promise = contract.claim(id.to_string());
    amount
}

pub fn claim_refund(contract: &mut Contract, account: &str, id: &str, now: u64) -> u128 {
    set_env(account, now);
    let amount = contract.get_claimable(id.to_string(), acct(account)).0;
    let _promise = contract.claim_refund(id.to_string());
    amount
}

/// Executes the private claim callback with a mocked FT transfer result.
pub fn settle_claim(
    contract: &mut Contract,
    account: &str,
    id: &str,
    amount: u128,
    success: bool,
    now: u64,
) {
    let result = if success {
        PromiseResult::Successful(vec![])
    } else {
        PromiseResult::Failed
    };
    set_env_with_results(CONTRACT, now, vec![result]);
    contract.on_claim_transfer(id.to_string(), acct(account), U128(amount));
}

pub fn claim_and_settle(
    contract: &mut Contract,
    account: &str,
    id: &str,
    success: bool,
    now: u64,
) -> u128 {
    let amount = claim(contract, account, id, now);
    settle_claim(contract, account, id, amount, success, now);
    amount
}
