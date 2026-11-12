//! Stored state, input and view types for the Notch market contract.
//!
//! Money is always unsigned integer base units of the configured NEP-141
//! collateral token. Timestamps are nanoseconds since the Unix epoch as
//! returned by `env::block_timestamp()`.
//!
//! The accounting in this module is deliberately market-mode agnostic: a
//! Trend Battle is a binary market with two defined choices, so it reuses the
//! same totals, positions and pooled payout formula as Trend Trading.

use near_sdk::borsh::{BorshDeserialize, BorshSerialize};
use near_sdk::json_types::{U128, U64};
use near_sdk::AccountId;
use serde::{Deserialize, Serialize};

use crate::math::pooled_payout;

pub type MarketId = String;

/// Number of outcomes in every Notch binary market (Trend Trading or Battle).
pub const NUM_OUTCOMES: usize = 2;
/// First choice index (Trend Trading: UP, Battle: topic A).
pub const OUTCOME_A: u8 = 0;
/// Second choice index (Trend Trading: DOWN, Battle: topic B).
pub const OUTCOME_B: u8 = 1;

/// S1 ships with zero fees. Kept explicit in the config/view surface.
pub const FEE_BPS: u16 = 0;

// ---------------------------------------------------------------------------
// Stored enums
// ---------------------------------------------------------------------------

#[derive(
    BorshSerialize, BorshDeserialize, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq,
)]
#[serde(rename_all = "snake_case")]
pub enum MarketMode {
    TrendTrading,
    /// Two topics compared under one frozen rule. Uses identical escrow and
    /// payout accounting; only configuration and resolution semantics differ.
    TrendBattle,
}

impl MarketMode {
    pub fn as_str(&self) -> &'static str {
        match self {
            MarketMode::TrendTrading => "trend_trading",
            MarketMode::TrendBattle => "trend_battle",
        }
    }
}

#[derive(BorshSerialize, BorshDeserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum MarketStatus {
    /// Entries are accepted while `open_at <= now < close_at`.
    Open,
    /// Entry window elapsed; awaiting resolution or void.
    Closed,
    /// Winning outcome frozen; claims are open.
    Resolved,
    /// Market invalidated; refunds are open.
    Voided,
}

impl MarketStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            MarketStatus::Open => "open",
            MarketStatus::Closed => "closed",
            MarketStatus::Resolved => "resolved",
            MarketStatus::Voided => "voided",
        }
    }

    pub fn is_final(&self) -> bool {
        matches!(self, MarketStatus::Resolved | MarketStatus::Voided)
    }
}

/// S1 supports one invalidation policy: a void refunds every stake in full.
/// The field is part of the immutable market configuration so later policies
/// can be added without changing already-created markets.
#[derive(
    BorshSerialize, BorshDeserialize, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq,
)]
#[serde(rename_all = "snake_case")]
pub enum InvalidationPolicy {
    RefundOnVoid,
}

impl InvalidationPolicy {
    pub fn as_str(&self) -> &'static str {
        match self {
            InvalidationPolicy::RefundOnVoid => "refund_on_void",
        }
    }
}

/// Frozen battle comparison formulas. S2 supports exactly one version so an
/// operator cannot create a battle with an unknown or ambiguous formula.
#[derive(
    BorshSerialize, BorshDeserialize, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq,
)]
#[serde(rename_all = "snake_case")]
pub enum BattleFormula {
    GrowthComparisonV1,
}

impl BattleFormula {
    pub fn as_str(&self) -> &'static str {
        match self {
            BattleFormula::GrowthComparisonV1 => "growth_comparison_v1",
        }
    }
}

/// Precommitted tie handling. S2 supports only VOID: when the measured growth
/// difference is within the frozen tolerance, no winner is invented and all
/// stakes are refunded.
#[derive(
    BorshSerialize, BorshDeserialize, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq,
)]
#[serde(rename_all = "snake_case")]
pub enum TiePolicy {
    Void,
}

impl TiePolicy {
    pub fn as_str(&self) -> &'static str {
        match self {
            TiePolicy::Void => "void",
        }
    }
}

/// How a final market state was reached. Kept explicit so clients can
/// distinguish a winning-outcome resolution, a manual void and a battle tie.
#[derive(BorshSerialize, BorshDeserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum ResolutionKind {
    WinningOutcome,
    Void,
    Tie,
}

impl ResolutionKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            ResolutionKind::WinningOutcome => "winning_outcome",
            ResolutionKind::Void => "void",
            ResolutionKind::Tie => "tie",
        }
    }
}

/// One side of a Trend Battle. Both topics must use the same source, project
/// and metric so the comparison is apples-to-apples.
#[derive(BorshSerialize, BorshDeserialize, Serialize, Deserialize, Clone, Debug, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BattleTopic {
    /// Stable public topic key, e.g. `ai-agents`.
    pub topic_id: String,
    /// Frozen data source identifier, e.g. `wikimedia-pageviews-v1`.
    pub source_id: String,
    /// Frozen project, e.g. `en.wikipedia.org`.
    pub project: String,
    /// Frozen canonical article title used for measurement.
    pub article_title: String,
    /// Frozen metric identifier, e.g. `daily-pageviews-growth-v1`.
    pub metric: String,
}

/// Immutable battle configuration stored onchain.
#[derive(BorshSerialize, BorshDeserialize, Clone, Debug, PartialEq, Eq)]
pub struct BattleConfig {
    pub topic_a: BattleTopic,
    pub topic_b: BattleTopic,
    /// Shared observation window start (ns since Unix epoch).
    pub observation_start: u64,
    /// Shared observation window end (ns since Unix epoch).
    pub observation_end: u64,
    pub formula: BattleFormula,
    /// Minimum baseline pageviews per topic; prevents microscopic-denominator
    /// artifacts and is frozen before entry.
    pub min_baseline_views: u64,
    /// Absolute growth-difference threshold in basis points. A difference at
    /// or below this value must be settled as a tie (void/refund).
    pub tie_tolerance_bps: u16,
    pub tie_policy: TiePolicy,
}

// ---------------------------------------------------------------------------
// Stored state
// ---------------------------------------------------------------------------

#[derive(BorshSerialize, BorshDeserialize, Clone, Debug)]
pub struct Config {
    pub owner: AccountId,
    /// Creates markets and may pause entries.
    pub operator: AccountId,
    /// Only this account may record a final outcome.
    pub resolver: AccountId,
    /// The single NEP-141 token accepted as collateral.
    pub collateral_token: AccountId,
    /// Smallest accepted entry, in token base units.
    pub min_entry_amount: u128,
    /// Pauses new markets and new entries; claims/refunds stay open.
    pub entries_paused: bool,
}

#[derive(BorshSerialize, BorshDeserialize, Clone, Debug)]
pub struct Market {
    pub market_id: MarketId,
    pub mode: MarketMode,
    pub question: String,
    pub choices: [String; 2],
    pub source_id: String,
    /// Frozen rule digest, `sha256:<64 lowercase/uppercase hex chars>`.
    pub rule_hash: String,
    pub open_at: u64,
    pub close_at: u64,
    pub resolve_after: u64,
    pub invalidation_policy: InvalidationPolicy,
    pub status: MarketStatus,
    pub totals: [u128; 2],
    pub escrow_total: u128,
    /// Confirmed outgoing transfers (payouts + refunds).
    pub paid_total: u128,
    /// Outgoing transfers currently in flight.
    pub pending_total: u128,
    pub winning_outcome: Option<u8>,
    pub evidence_hash: Option<String>,
    pub void_reason_hash: Option<String>,
    pub created_at: u64,
    pub resolved_at: Option<u64>,
    pub voided_at: Option<u64>,
    /// Battle-only configuration; `None` for Trend Trading.
    pub battle: Option<BattleConfig>,
    /// Set exactly once when the market becomes final.
    pub resolution_kind: Option<ResolutionKind>,
}

impl Market {
    /// Entries are accepted only inside the immutable time window while the
    /// market is open and the contract is not paused for entries.
    pub fn is_entries_open(&self, now: u64, entries_paused: bool) -> bool {
        !entries_paused
            && self.status == MarketStatus::Open
            && now >= self.open_at
            && now < self.close_at
    }

    pub fn winning_total(&self) -> u128 {
        match self.winning_outcome {
            Some(outcome) => self.totals[outcome as usize],
            None => 0,
        }
    }

    /// Gross entitlement from the frozen market result, before claims.
    /// Fees are zero by design.
    pub fn gross_entitlement(&self, position: &Position) -> u128 {
        match self.status {
            MarketStatus::Resolved => {
                let winning =
                    self.winning_outcome
                        .expect("resolved market without outcome") as usize;
                let stake = position.stakes[winning];
                if stake == 0 {
                    return 0;
                }
                pooled_payout(stake, self.escrow_total, self.totals[winning])
            }
            MarketStatus::Voided => position
                .stakes
                .iter()
                .fold(0u128, |acc, stake| acc.saturating_add(*stake)),
            MarketStatus::Open | MarketStatus::Closed => 0,
        }
    }

    /// Amount the account can claim right now (0 while a transfer is pending).
    pub fn claimable_for(&self, position: &Position) -> u128 {
        self.gross_entitlement(position)
            .saturating_sub(position.claimed_total)
            .saturating_sub(position.pending_amount)
    }

    /// Escrow not yet paid out or in flight. Includes rounding dust and
    /// stakes nobody has claimed yet.
    pub fn unclaimed_reserve(&self) -> u128 {
        self.escrow_total
            .saturating_sub(self.paid_total)
            .saturating_sub(self.pending_total)
    }
}

#[derive(BorshSerialize, BorshDeserialize, Clone, Debug, Default)]
pub struct Position {
    pub stakes: [u128; 2],
    pub claimed_total: u128,
    pub pending_amount: u128,
}

impl Position {
    pub fn total_stake(&self) -> u128 {
        self.stakes
            .iter()
            .fold(0u128, |acc, stake| acc.saturating_add(*stake))
    }
}

#[derive(BorshSerialize, BorshDeserialize, Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct PositionKey {
    pub market_id: MarketId,
    pub account_id: AccountId,
}

// ---------------------------------------------------------------------------
// Input types (JSON)
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(deny_unknown_fields)]
pub struct CreateMarketArgs {
    pub market_id: MarketId,
    pub mode: MarketMode,
    pub question: String,
    /// Exactly two labels, e.g. `["UP", "DOWN"]`. Index 0 is outcome 0.
    pub choices: Vec<String>,
    pub source_id: String,
    /// `sha256:<hex>` commitment to the frozen resolution rule.
    pub rule_hash: String,
    pub open_at: U64,
    pub close_at: U64,
    pub resolve_after: U64,
    pub invalidation_policy: InvalidationPolicy,
    /// Required for `trend_battle`, forbidden for `trend_trading`.
    #[serde(default)]
    pub battle: Option<BattleConfigArgs>,
}

/// JSON input for battle configuration. Timestamps are strings (`U64`).
#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(deny_unknown_fields)]
pub struct BattleConfigArgs {
    pub topic_a: BattleTopic,
    pub topic_b: BattleTopic,
    pub observation_start: U64,
    pub observation_end: U64,
    pub formula: BattleFormula,
    pub min_baseline_views: U64,
    pub tie_tolerance_bps: u16,
    pub tie_policy: TiePolicy,
}

impl BattleConfigArgs {
    pub fn into_config(self) -> BattleConfig {
        BattleConfig {
            topic_a: self.topic_a,
            topic_b: self.topic_b,
            observation_start: self.observation_start.0,
            observation_end: self.observation_end.0,
            formula: self.formula,
            min_baseline_views: self.min_baseline_views.0,
            tie_tolerance_bps: self.tie_tolerance_bps,
            tie_policy: self.tie_policy,
        }
    }
}

/// NEP-141 `msg` payload for a position entry.
#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(deny_unknown_fields)]
pub struct EntryMessage {
    pub market_id: MarketId,
    /// 0 = first choice, 1 = second choice.
    pub outcome: u8,
}

// ---------------------------------------------------------------------------
// Stable view types
// ---------------------------------------------------------------------------

#[derive(Serialize, Clone, Debug)]
pub struct MarketView {
    pub market_id: MarketId,
    pub mode: String,
    pub question: String,
    pub choices: [String; 2],
    pub source_id: String,
    pub rule_hash: String,
    pub open_at: U64,
    pub close_at: U64,
    pub resolve_after: U64,
    pub invalidation_policy: String,
    pub status: String,
    pub entries_open: bool,
    pub entries_paused: bool,
    pub totals: [U128; 2],
    pub escrow_total: U128,
    pub paid_total: U128,
    pub pending_total: U128,
    pub unclaimed_reserve: U128,
    pub winning_outcome: Option<u8>,
    pub winning_choice: Option<String>,
    pub evidence_hash: Option<String>,
    pub void_reason_hash: Option<String>,
    pub created_at: U64,
    pub resolved_at: Option<U64>,
    pub voided_at: Option<U64>,
    pub fee_bps: u16,
    /// `winning_outcome` | `void` | `tie` | null while not final.
    pub resolution_kind: Option<String>,
    /// Battle configuration for `trend_battle`; null for `trend_trading`.
    pub battle: Option<BattleConfigView>,
}

#[derive(Serialize, Clone, Debug)]
pub struct BattleConfigView {
    pub topic_a: BattleTopic,
    pub topic_b: BattleTopic,
    pub observation_start: U64,
    pub observation_end: U64,
    pub formula: String,
    pub min_baseline_views: U64,
    pub tie_tolerance_bps: u16,
    pub tie_policy: String,
}

impl From<&BattleConfig> for BattleConfigView {
    fn from(config: &BattleConfig) -> Self {
        Self {
            topic_a: config.topic_a.clone(),
            topic_b: config.topic_b.clone(),
            observation_start: config.observation_start.into(),
            observation_end: config.observation_end.into(),
            formula: config.formula.as_str().to_string(),
            min_baseline_views: config.min_baseline_views.into(),
            tie_tolerance_bps: config.tie_tolerance_bps,
            tie_policy: config.tie_policy.as_str().to_string(),
        }
    }
}

#[derive(Serialize, Clone, Debug)]
pub struct PositionView {
    pub market_id: MarketId,
    pub account_id: AccountId,
    pub stakes: [U128; 2],
    pub total_stake: U128,
    pub claimed_total: U128,
    pub pending_amount: U128,
    pub claimable: U128,
    /// `open` | `pending` | `claimable` | `claimed` | `not_eligible`
    pub claim_state: String,
}

#[derive(Serialize, Clone, Debug)]
pub struct MarketTotalsView {
    pub market_id: MarketId,
    pub status: String,
    pub resolution_kind: Option<String>,
    pub totals: [U128; 2],
    pub winning_pool: Option<U128>,
    pub escrow_total: U128,
    pub paid_total: U128,
    pub pending_total: U128,
    pub unclaimed_reserve: U128,
}

#[derive(Serialize, Clone, Debug)]
pub struct ConfigView {
    pub owner: AccountId,
    pub operator: AccountId,
    pub resolver: AccountId,
    pub collateral_token: AccountId,
    pub min_entry_amount: U128,
    pub entries_paused: bool,
    pub market_count: u64,
    pub fee_bps: u16,
}

pub fn claim_state(market: &Market, position: &Position) -> &'static str {
    if position.pending_amount > 0 {
        return "pending";
    }
    if !market.status.is_final() {
        return "open";
    }
    let claimable = market.claimable_for(position);
    if claimable > 0 {
        return "claimable";
    }
    if market.gross_entitlement(position) > 0 {
        return "claimed";
    }
    "not_eligible"
}
