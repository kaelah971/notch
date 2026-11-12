//! Notch — shared NEAR market settlement engine (S1: Near Market Contract Core).
//!
//! One binary pooled market engine for Trend Trading and (later) Trend Battles:
//! NEP-141 escrow, resolver-authorized settlement, fully collateralized payouts
//! and void refunds, with idempotent, callback-confirmed claims.
//!
//! Invariants:
//! - Only the configured collateral token may fund a market.
//! - `escrow_total[t] == sum(stakes)` for every market at all times.
//! - A payout is never marked paid until the FT `ft_transfer` callback reports
//!   success.
//! - Sum of confirmed + pending + unclaimed reserve never exceeds escrow.
//! - A resolved outcome and its evidence hash are immutable; only a void is
//!   possible before resolution.
//! - Fees are zero.

mod math;
mod types;

pub use types::*;

use near_sdk::borsh::BorshSerialize;
use near_sdk::json_types::U128;
use near_sdk::store::LookupMap;
use near_sdk::{
    env, ext_contract, near, require, AccountId, BorshStorageKey, Gas, NearToken, PanicOnDefault,
    Promise, PromiseOrValue,
};

/// Gas allocated to the collateral token's `ft_transfer`.
pub const GAS_FOR_FT_TRANSFER: Gas = Gas::from_tgas(25);
/// Gas allocated to the claim finalization callback.
pub const GAS_FOR_CLAIM_CALLBACK: Gas = Gas::from_tgas(20);
/// Maximum number of markets returned by `list_markets`.
pub const MAX_LIST_LIMIT: u32 = 50;

const MAX_QUESTION_LEN: usize = 500;
const MAX_CHOICE_LEN: usize = 64;
const MAX_SOURCE_ID_LEN: usize = 128;
const MAX_MARKET_ID_LEN: usize = 64;
const MAX_ENTRY_MSG_LEN: usize = 512;
const MAX_TOPIC_ID_LEN: usize = 64;
const MAX_PROJECT_LEN: usize = 128;
const MAX_ARTICLE_TITLE_LEN: usize = 256;
const MAX_METRIC_LEN: usize = 64;
const MAX_TIE_TOLERANCE_BPS: u16 = 10_000;

#[derive(BorshSerialize, BorshStorageKey)]
enum StorageKey {
    Markets,
    Positions,
}

#[ext_contract(ext_ft)]
pub trait FungibleToken {
    fn ft_transfer(&mut self, receiver_id: AccountId, amount: U128, memo: Option<String>);
}

#[ext_contract(ext_self)]
pub trait ClaimReceiver {
    fn on_claim_transfer(&mut self, market_id: MarketId, account_id: AccountId, amount: U128);
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    config: Config,
    markets: LookupMap<MarketId, Market>,
    positions: LookupMap<PositionKey, Position>,
    market_ids: Vec<MarketId>,
}

// ---------------------------------------------------------------------------
// Initialization and administration
// ---------------------------------------------------------------------------

#[near]
impl Contract {
    /// One-time initialization. `#[init]` rejects any second call.
    #[init]
    pub fn new(
        owner: AccountId,
        operator: AccountId,
        resolver: AccountId,
        collateral_token: AccountId,
        min_entry_amount: U128,
    ) -> Self {
        // Defense in depth: `#[init]` already guards the exported entry point.
        require!(!env::state_exists(), "ERR_ALREADY_INITIALIZED");
        require!(min_entry_amount.0 > 0, "ERR_MIN_ENTRY_ZERO");
        Self {
            config: Config {
                owner,
                operator,
                resolver,
                collateral_token,
                min_entry_amount: min_entry_amount.0,
                entries_paused: false,
            },
            markets: LookupMap::new(StorageKey::Markets),
            positions: LookupMap::new(StorageKey::Positions),
            market_ids: Vec::new(),
        }
    }

    /// Owner-only. Changing the operator affects future market creation and
    /// pause calls only; market configuration stays immutable.
    pub fn set_operator(&mut self, operator: AccountId) {
        self.assert_owner();
        let previous = self.config.operator.clone();
        self.config.operator = operator.clone();
        emit_event(
            "config_updated",
            serde_json::json!({
                "field": "operator",
                "old": previous,
                "new": operator,
                "predecessor": env::predecessor_account_id(),
            }),
        );
    }

    /// Owner-only. Changing the resolver does not alter already-resolved
    /// markets; it only authorizes future resolutions and voids.
    pub fn set_resolver(&mut self, resolver: AccountId) {
        self.assert_owner();
        let previous = self.config.resolver.clone();
        self.config.resolver = resolver.clone();
        emit_event(
            "config_updated",
            serde_json::json!({
                "field": "resolver",
                "old": previous,
                "new": resolver,
                "predecessor": env::predecessor_account_id(),
            }),
        );
    }

    /// Owner or operator. Pauses market creation and new entries. Claims and
    /// refunds remain available while paused.
    pub fn set_entries_paused(&mut self, paused: bool) -> bool {
        let predecessor = env::predecessor_account_id();
        require!(
            predecessor == self.config.owner || predecessor == self.config.operator,
            "ERR_NOT_AUTHORIZED"
        );
        self.config.entries_paused = paused;
        emit_event(
            "entries_paused_updated",
            serde_json::json!({ "paused": paused, "predecessor": predecessor }),
        );
        paused
    }

    // -----------------------------------------------------------------------
    // Market creation
    // -----------------------------------------------------------------------

    /// Operator-only market creation. The resulting configuration is
    /// immutable: no update method exists for it.
    ///
    /// Timestamp arguments are nanoseconds since the Unix epoch and must
    /// satisfy `open_at < close_at <= resolve_after`. `close_at` must be in
    /// the future.
    pub fn create_market(&mut self, args: CreateMarketArgs) -> MarketView {
        self.assert_operator();
        require!(!self.config.entries_paused, "ERR_ENTRIES_PAUSED");

        let now = env::block_timestamp();
        require!(is_valid_market_id(&args.market_id), "ERR_INVALID_MARKET_ID");
        require!(
            !self.markets.contains_key(&args.market_id),
            "ERR_MARKET_EXISTS"
        );
        // Mode-specific configuration is validated and frozen here. Both modes
        // then use the same escrow, position and payout engine.
        let battle = match args.mode {
            MarketMode::TrendTrading => {
                require!(args.battle.is_none(), "ERR_UNEXPECTED_BATTLE_CONFIG");
                None
            }
            MarketMode::TrendBattle => {
                let Some(battle_args) = args.battle.as_ref() else {
                    env::panic_str("ERR_MISSING_BATTLE_CONFIG");
                };
                if let Err(code) =
                    validate_battle_config(battle_args, &args.source_id, args.resolve_after.0)
                {
                    env::panic_str(code);
                }
                Some(battle_args.clone().into_config())
            }
        };
        require!(
            is_valid_text(&args.question, MAX_QUESTION_LEN),
            "ERR_INVALID_QUESTION"
        );
        require!(args.choices.len() == NUM_OUTCOMES, "ERR_INVALID_CHOICES");
        require!(
            is_valid_text(&args.choices[0], MAX_CHOICE_LEN)
                && is_valid_text(&args.choices[1], MAX_CHOICE_LEN),
            "ERR_INVALID_CHOICES"
        );
        require!(args.choices[0] != args.choices[1], "ERR_INVALID_CHOICES");
        require!(
            is_valid_text(&args.source_id, MAX_SOURCE_ID_LEN),
            "ERR_INVALID_SOURCE_ID"
        );
        require!(is_valid_digest(&args.rule_hash), "ERR_INVALID_RULE_HASH");
        require!(args.open_at.0 < args.close_at.0, "ERR_INVALID_TIME_WINDOW");
        require!(args.close_at.0 > now, "ERR_MARKET_ALREADY_CLOSED");
        require!(
            args.resolve_after.0 >= args.close_at.0,
            "ERR_INVALID_RESOLVE_TIME"
        );
        require!(
            args.invalidation_policy == InvalidationPolicy::RefundOnVoid,
            "ERR_INVALID_INVALIDATION_POLICY"
        );

        let market = Market {
            market_id: args.market_id.clone(),
            mode: args.mode,
            question: args.question.clone(),
            choices: [args.choices[0].clone(), args.choices[1].clone()],
            source_id: args.source_id.clone(),
            rule_hash: args.rule_hash.clone(),
            open_at: args.open_at.0,
            close_at: args.close_at.0,
            resolve_after: args.resolve_after.0,
            invalidation_policy: args.invalidation_policy,
            status: MarketStatus::Open,
            totals: [0, 0],
            escrow_total: 0,
            paid_total: 0,
            pending_total: 0,
            winning_outcome: None,
            evidence_hash: None,
            void_reason_hash: None,
            created_at: now,
            resolved_at: None,
            voided_at: None,
            battle,
            resolution_kind: None,
        };
        let view = self.market_view(&market, now);

        self.markets.insert(args.market_id.clone(), market);
        self.market_ids.push(args.market_id.clone());
        self.markets.flush();

        emit_event(
            "market_created",
            serde_json::json!({
                "market_id": args.market_id,
                "mode": args.mode.as_str(),
                "open_at": args.open_at.0,
                "close_at": args.close_at.0,
                "resolve_after": args.resolve_after.0,
                "rule_hash": args.rule_hash,
                "source_id": args.source_id,
            }),
        );

        view
    }

    // -----------------------------------------------------------------------
    // NEP-141 entry
    // -----------------------------------------------------------------------

    /// NEP-141 receiver entry point.
    ///
    /// `msg` is `{"market_id":"<id>","outcome":0|1}`. Returns `U128(0)` when
    /// the whole amount was used, or `U128(amount)` to instruct the token
    /// contract to refund the sender. All validation happens before any state
    /// mutation.
    pub fn ft_on_transfer(
        &mut self,
        sender_id: AccountId,
        amount: U128,
        msg: String,
    ) -> PromiseOrValue<U128> {
        if env::predecessor_account_id() != self.config.collateral_token {
            emit_entry_rejected(None, &sender_id, amount.0, "wrong_token");
            return PromiseOrValue::Value(amount);
        }

        if msg.len() > MAX_ENTRY_MSG_LEN {
            emit_entry_rejected(None, &sender_id, amount.0, "malformed_message");
            return PromiseOrValue::Value(amount);
        }

        let entry: EntryMessage = match serde_json::from_str(&msg) {
            Ok(entry) => entry,
            Err(_) => {
                emit_entry_rejected(None, &sender_id, amount.0, "malformed_message");
                return PromiseOrValue::Value(amount);
            }
        };

        if let Err(reason) = self.record_entry(&entry, &sender_id, amount.0) {
            emit_entry_rejected(Some(&entry.market_id), &sender_id, amount.0, reason);
            return PromiseOrValue::Value(amount);
        }

        PromiseOrValue::Value(U128(0))
    }

    // -----------------------------------------------------------------------
    // Lifecycle
    // -----------------------------------------------------------------------

    /// Permissionless, time-guarded Open -> Closed transition. Idempotent.
    pub fn close_market(&mut self, market_id: MarketId) -> MarketView {
        let now = env::block_timestamp();
        let mut market = self.load_market(&market_id);
        require!(now >= market.close_at, "ERR_ENTRY_WINDOW_OPEN");

        match market.status {
            MarketStatus::Open => {
                market.status = MarketStatus::Closed;
                let view = self.market_view(&market, now);
                self.markets.insert(market_id.clone(), market);
                self.markets.flush();
                emit_event(
                    "market_closed",
                    serde_json::json!({ "market_id": market_id, "closed_at": now }),
                );
                return view;
            }
            MarketStatus::Closed => {}
            _ => env::panic_str("ERR_MARKET_FINALIZED"),
        }

        self.market_view(&market, now)
    }

    /// Resolver-only final outcome. Only valid after `resolve_after`, and only
    /// when the winning side holds stake (otherwise the market must be voided).
    ///
    /// Repeating the exact same resolution is a no-op success; any conflicting
    /// resolution is rejected. The evidence hash is a commitment to external
    /// evidence, not a claim of source truth.
    pub fn resolve_market(
        &mut self,
        market_id: MarketId,
        winning_outcome: u8,
        evidence_hash: String,
    ) -> MarketView {
        self.assert_resolver();
        let now = env::block_timestamp();
        let mut market = self.load_market(&market_id);

        match market.status {
            MarketStatus::Resolved => {
                require!(
                    market.winning_outcome == Some(winning_outcome)
                        && market.evidence_hash.as_deref() == Some(evidence_hash.as_str()),
                    "ERR_ALREADY_RESOLVED"
                );
                return self.market_view(&market, now);
            }
            MarketStatus::Voided => env::panic_str("ERR_MARKET_VOIDED"),
            MarketStatus::Open | MarketStatus::Closed => {}
        }

        require!(
            (winning_outcome as usize) < NUM_OUTCOMES,
            "ERR_INVALID_OUTCOME"
        );
        require!(is_valid_digest(&evidence_hash), "ERR_INVALID_EVIDENCE_HASH");
        require!(now >= market.resolve_after, "ERR_RESOLVE_TOO_EARLY");
        require!(
            market.totals[winning_outcome as usize] > 0,
            "ERR_NO_WINNING_STAKE"
        );

        let winning_choice = market.choices[winning_outcome as usize].clone();
        let escrow_total = market.escrow_total;
        let winning_pool = market.totals[winning_outcome as usize];

        market.status = MarketStatus::Resolved;
        market.winning_outcome = Some(winning_outcome);
        market.evidence_hash = Some(evidence_hash.clone());
        market.resolved_at = Some(now);
        market.resolution_kind = Some(ResolutionKind::WinningOutcome);
        let view = self.market_view(&market, now);
        self.markets.insert(market_id.clone(), market);
        self.markets.flush();

        emit_event(
            "market_resolved",
            serde_json::json!({
                "market_id": market_id,
                "winning_outcome": winning_outcome,
                "winning_choice": winning_choice,
                "evidence_hash": evidence_hash,
                "resolved_at": now,
                "escrow_total": escrow_total.to_string(),
                "winning_pool": winning_pool.to_string(),
            }),
        );

        view
    }

    /// Owner- or resolver-authorized invalidation. A resolved market cannot be
    /// voided, so a frozen outcome is never rewritten. Repeating the same void
    /// reason is a no-op success; a different reason is rejected.
    pub fn void_market(&mut self, market_id: MarketId, reason_hash: String) -> MarketView {
        let predecessor = env::predecessor_account_id();
        require!(
            predecessor == self.config.resolver || predecessor == self.config.owner,
            "ERR_NOT_AUTHORIZED"
        );
        require!(is_valid_digest(&reason_hash), "ERR_INVALID_REASON_HASH");

        let now = env::block_timestamp();
        let mut market = self.load_market(&market_id);

        match market.status {
            MarketStatus::Voided => {
                require!(
                    market.void_reason_hash.as_deref() == Some(reason_hash.as_str()),
                    "ERR_ALREADY_VOIDED"
                );
                return self.market_view(&market, now);
            }
            MarketStatus::Resolved => env::panic_str("ERR_MARKET_RESOLVED"),
            MarketStatus::Open | MarketStatus::Closed => {}
        }

        market.status = MarketStatus::Voided;
        market.void_reason_hash = Some(reason_hash.clone());
        market.voided_at = Some(now);
        market.resolution_kind = Some(ResolutionKind::Void);
        let view = self.market_view(&market, now);
        self.markets.insert(market_id.clone(), market);
        self.markets.flush();

        emit_event(
            "market_voided",
            serde_json::json!({
                "market_id": market_id,
                "reason_hash": reason_hash,
                "voided_at": now,
            }),
        );

        view
    }

    /// Resolver-only tie settlement for a Trend Battle.
    ///
    /// The resolver asserts that the measured growth difference is within the
    /// frozen `tie_tolerance_bps`. The market does not invent a winner: it
    /// becomes VOID under its precommitted tie policy and every stake is
    /// refundable. `evidence_hash` commits to the calculation evidence.
    ///
    /// Repeating the same tie evidence is a no-op success; any other attempt
    /// to finalize the market is rejected.
    pub fn resolve_tie(&mut self, market_id: MarketId, evidence_hash: String) -> MarketView {
        self.assert_resolver();
        require!(is_valid_digest(&evidence_hash), "ERR_INVALID_EVIDENCE_HASH");

        let now = env::block_timestamp();
        let mut market = self.load_market(&market_id);
        require!(
            market.mode == MarketMode::TrendBattle,
            "ERR_NOT_BATTLE_MARKET"
        );

        match market.status {
            MarketStatus::Voided => {
                require!(
                    market.resolution_kind == Some(ResolutionKind::Tie)
                        && market.evidence_hash.as_deref() == Some(evidence_hash.as_str()),
                    "ERR_ALREADY_VOIDED"
                );
                return self.market_view(&market, now);
            }
            MarketStatus::Resolved => env::panic_str("ERR_MARKET_RESOLVED"),
            MarketStatus::Open | MarketStatus::Closed => {}
        }

        require!(now >= market.resolve_after, "ERR_RESOLVE_TOO_EARLY");

        let battle = match market.battle.as_ref() {
            Some(battle) => battle,
            None => env::panic_str("ERR_MISSING_BATTLE_CONFIG"),
        };
        require!(
            battle.tie_policy == TiePolicy::Void,
            "ERR_INVALID_TIE_POLICY"
        );

        let tie_tolerance_bps = battle.tie_tolerance_bps;
        let topic_a = battle.topic_a.topic_id.clone();
        let topic_b = battle.topic_b.topic_id.clone();

        market.status = MarketStatus::Voided;
        market.resolution_kind = Some(ResolutionKind::Tie);
        market.winning_outcome = None;
        market.evidence_hash = Some(evidence_hash.clone());
        market.voided_at = Some(now);
        let view = self.market_view(&market, now);
        self.markets.insert(market_id.clone(), market);
        self.markets.flush();

        emit_event(
            "market_tie_voided",
            serde_json::json!({
                "market_id": market_id,
                "topic_a": topic_a,
                "topic_b": topic_b,
                "tie_tolerance_bps": tie_tolerance_bps,
                "evidence_hash": evidence_hash,
                "voided_at": now,
            }),
        );

        view
    }

    // -----------------------------------------------------------------------
    // Claims and refunds
    // -----------------------------------------------------------------------

    /// Claim a resolved payout or a void refund. The transfer is marked
    /// pending before the FT call and only finalized in the callback.
    pub fn claim(&mut self, market_id: MarketId) -> Promise {
        let account_id = env::predecessor_account_id();
        self.start_claim(market_id, account_id, false)
    }

    /// Explicit refund path for a voided market. Returns the original stake
    /// once; a resolved market is rejected.
    pub fn claim_refund(&mut self, market_id: MarketId) -> Promise {
        let account_id = env::predecessor_account_id();
        self.start_claim(market_id, account_id, true)
    }

    /// Private callback for the collateral token transfer. `#[private]` limits
    /// callers to the contract account itself.
    #[private]
    pub fn on_claim_transfer(&mut self, market_id: MarketId, account_id: AccountId, amount: U128) {
        // Defense in depth: `#[private]` already restricts the exported entry
        // point to the contract account.
        require!(
            env::predecessor_account_id() == env::current_account_id(),
            "ERR_ONLY_SELF"
        );
        let amount = amount.0;
        let key = PositionKey {
            market_id: market_id.clone(),
            account_id: account_id.clone(),
        };

        let mut market = self.load_market(&market_id);
        let mut position = match self.positions.get(&key).cloned() {
            Some(position) => position,
            None => env::panic_str("ERR_POSITION_NOT_FOUND"),
        };

        require!(
            market.pending_total >= amount && position.pending_amount >= amount,
            "ERR_INCONSISTENT_STATE"
        );

        market.pending_total -= amount;
        position.pending_amount -= amount;

        let succeeded = env::promise_result_checked(0, usize::MAX).is_ok();
        if succeeded {
            position.claimed_total = position
                .claimed_total
                .checked_add(amount)
                .unwrap_or_else(|| env::panic_str("ERR_OVERFLOW"));
            market.paid_total = market
                .paid_total
                .checked_add(amount)
                .unwrap_or_else(|| env::panic_str("ERR_OVERFLOW"));

            self.markets.insert(market_id.clone(), market);
            self.positions.insert(key, position);
            self.markets.flush();
            self.positions.flush();

            emit_event(
                "claim_settled",
                serde_json::json!({
                    "market_id": market_id,
                    "account_id": account_id,
                    "amount": amount.to_string(),
                }),
            );
        } else {
            // The transfer failed. Restore claimability; the escrow never left
            // the contract, so the user may retry safely.
            self.markets.insert(market_id.clone(), market);
            self.positions.insert(key, position);
            self.markets.flush();
            self.positions.flush();

            emit_event(
                "claim_failed",
                serde_json::json!({
                    "market_id": market_id,
                    "account_id": account_id,
                    "amount": amount.to_string(),
                    "reason": "ft_transfer_failed",
                }),
            );
        }
    }

    // -----------------------------------------------------------------------
    // Views
    // -----------------------------------------------------------------------

    pub fn get_market(&self, market_id: MarketId) -> Option<MarketView> {
        self.markets
            .get(&market_id)
            .map(|market| self.market_view(market, env::block_timestamp()))
    }

    pub fn get_position(&self, market_id: MarketId, account_id: AccountId) -> Option<PositionView> {
        let market = self.markets.get(&market_id)?;
        let key = PositionKey {
            market_id: market_id.clone(),
            account_id: account_id.clone(),
        };
        let position = self.positions.get(&key)?;
        let claimable = market.claimable_for(position);
        Some(PositionView {
            market_id,
            account_id,
            stakes: [U128(position.stakes[0]), U128(position.stakes[1])],
            total_stake: U128(position.total_stake()),
            claimed_total: U128(position.claimed_total),
            pending_amount: U128(position.pending_amount),
            claimable: U128(claimable),
            claim_state: claim_state(market, position).to_string(),
        })
    }

    pub fn get_market_totals(&self, market_id: MarketId) -> Option<MarketTotalsView> {
        self.markets.get(&market_id).map(|market| MarketTotalsView {
            market_id,
            status: market.status.as_str().to_string(),
            resolution_kind: market.resolution_kind.map(|kind| kind.as_str().to_string()),
            totals: [U128(market.totals[0]), U128(market.totals[1])],
            winning_pool: market.winning_outcome.map(|_| U128(market.winning_total())),
            escrow_total: U128(market.escrow_total),
            paid_total: U128(market.paid_total),
            pending_total: U128(market.pending_total),
            unclaimed_reserve: U128(market.unclaimed_reserve()),
        })
    }

    /// Claimable amount right now, in token base units. Returns 0 while a
    /// claim transfer is pending and 0 for losing/unresolved positions.
    pub fn get_claimable(&self, market_id: MarketId, account_id: AccountId) -> U128 {
        let Some(market) = self.markets.get(&market_id) else {
            return U128(0);
        };
        let key = PositionKey {
            market_id,
            account_id,
        };
        match self.positions.get(&key) {
            Some(position) => U128(market.claimable_for(position)),
            None => U128(0),
        }
    }

    pub fn get_contract_config(&self) -> ConfigView {
        ConfigView {
            owner: self.config.owner.clone(),
            operator: self.config.operator.clone(),
            resolver: self.config.resolver.clone(),
            collateral_token: self.config.collateral_token.clone(),
            min_entry_amount: U128(self.config.min_entry_amount),
            entries_paused: self.config.entries_paused,
            market_count: self.market_ids.len() as u64,
            fee_bps: FEE_BPS,
        }
    }

    pub fn get_market_count(&self) -> u64 {
        self.market_ids.len() as u64
    }

    pub fn list_markets(&self, from_index: u64, limit: u32) -> Vec<MarketView> {
        let now = env::block_timestamp();
        let start = from_index as usize;
        let take = limit.min(MAX_LIST_LIMIT) as usize;
        self.market_ids
            .iter()
            .skip(start)
            .take(take)
            .filter_map(|id| {
                self.markets
                    .get(id)
                    .map(|market| self.market_view(market, now))
            })
            .collect()
    }

    // -----------------------------------------------------------------------
    // Internal helpers (not exported)
    // -----------------------------------------------------------------------

    fn assert_owner(&self) {
        require!(
            env::predecessor_account_id() == self.config.owner,
            "ERR_NOT_OWNER"
        );
    }

    fn assert_operator(&self) {
        require!(
            env::predecessor_account_id() == self.config.operator,
            "ERR_NOT_OPERATOR"
        );
    }

    fn assert_resolver(&self) {
        require!(
            env::predecessor_account_id() == self.config.resolver,
            "ERR_NOT_RESOLVER"
        );
    }

    fn load_market(&self, market_id: &str) -> Market {
        let key = market_id.to_string();
        match self.markets.get(&key).cloned() {
            Some(market) => market,
            None => env::panic_str("ERR_MARKET_NOT_FOUND"),
        }
    }

    fn market_view(&self, market: &Market, now: u64) -> MarketView {
        MarketView {
            market_id: market.market_id.clone(),
            mode: market.mode.as_str().to_string(),
            question: market.question.clone(),
            choices: market.choices.clone(),
            source_id: market.source_id.clone(),
            rule_hash: market.rule_hash.clone(),
            open_at: market.open_at.into(),
            close_at: market.close_at.into(),
            resolve_after: market.resolve_after.into(),
            invalidation_policy: market.invalidation_policy.as_str().to_string(),
            status: market.status.as_str().to_string(),
            entries_open: market.is_entries_open(now, self.config.entries_paused),
            entries_paused: self.config.entries_paused,
            totals: [U128(market.totals[0]), U128(market.totals[1])],
            escrow_total: U128(market.escrow_total),
            paid_total: U128(market.paid_total),
            pending_total: U128(market.pending_total),
            unclaimed_reserve: U128(market.unclaimed_reserve()),
            winning_outcome: market.winning_outcome,
            winning_choice: market
                .winning_outcome
                .map(|outcome| market.choices[outcome as usize].clone()),
            evidence_hash: market.evidence_hash.clone(),
            void_reason_hash: market.void_reason_hash.clone(),
            created_at: market.created_at.into(),
            resolved_at: market.resolved_at.map(Into::into),
            voided_at: market.voided_at.map(Into::into),
            fee_bps: FEE_BPS,
            resolution_kind: market.resolution_kind.map(|kind| kind.as_str().to_string()),
            battle: market.battle.as_ref().map(BattleConfigView::from),
        }
    }

    /// Returns `Err(reason)` for a rejected entry. No state is changed unless
    /// the entry is fully accepted.
    fn record_entry(
        &mut self,
        entry: &EntryMessage,
        sender: &AccountId,
        amount: u128,
    ) -> Result<(), &'static str> {
        let now = env::block_timestamp();
        let Some(mut market) = self.markets.get(&entry.market_id).cloned() else {
            return Err("unknown_market");
        };

        if self.config.entries_paused {
            return Err("entries_paused");
        }
        if market.status != MarketStatus::Open {
            return Err("market_not_open");
        }
        if now < market.open_at {
            return Err("before_open");
        }
        if now >= market.close_at {
            return Err("after_close");
        }
        if amount == 0 {
            return Err("amount_zero");
        }
        if amount < self.config.min_entry_amount {
            return Err("amount_below_minimum");
        }
        let side = entry.outcome as usize;
        if side >= NUM_OUTCOMES {
            return Err("invalid_outcome");
        }

        let key = PositionKey {
            market_id: entry.market_id.clone(),
            account_id: sender.clone(),
        };
        let mut position = self.positions.get(&key).cloned().unwrap_or_default();

        position.stakes[side] = match position.stakes[side].checked_add(amount) {
            Some(value) => value,
            None => return Err("amount_overflow"),
        };
        market.totals[side] = match market.totals[side].checked_add(amount) {
            Some(value) => value,
            None => return Err("amount_overflow"),
        };
        market.escrow_total = match market.escrow_total.checked_add(amount) {
            Some(value) => value,
            None => return Err("amount_overflow"),
        };

        self.markets.insert(entry.market_id.clone(), market.clone());
        self.positions.insert(key, position.clone());
        self.markets.flush();
        self.positions.flush();

        emit_event(
            "position_entered",
            serde_json::json!({
                "market_id": entry.market_id,
                "account_id": sender,
                "outcome": entry.outcome,
                "amount": amount.to_string(),
                "market_totals": [
                    market.totals[0].to_string(),
                    market.totals[1].to_string(),
                ],
                "account_stakes": [
                    position.stakes[0].to_string(),
                    position.stakes[1].to_string(),
                ],
                "sender_id": sender,
                "predecessor": env::predecessor_account_id(),
            }),
        );

        Ok(())
    }

    fn start_claim(
        &mut self,
        market_id: MarketId,
        account_id: AccountId,
        refund_only: bool,
    ) -> Promise {
        let mut market = self.load_market(&market_id);

        if refund_only {
            require!(
                market.status == MarketStatus::Voided,
                "ERR_MARKET_NOT_VOIDED"
            );
        } else {
            require!(market.status.is_final(), "ERR_MARKET_NOT_SETTLED");
        }

        let key = PositionKey {
            market_id: market_id.clone(),
            account_id: account_id.clone(),
        };
        let mut position = match self.positions.get(&key).cloned() {
            Some(position) => position,
            None => env::panic_str("ERR_NO_POSITION"),
        };

        require!(position.pending_amount == 0, "ERR_CLAIM_PENDING");
        let amount = market.claimable_for(&position);
        require!(amount > 0, "ERR_NOTHING_TO_CLAIM");

        // Persist the in-flight transfer before creating any promise. If the
        // promise fails or the transaction reverts, this is rolled back.
        position.pending_amount = amount;
        market.pending_total = market
            .pending_total
            .checked_add(amount)
            .unwrap_or_else(|| env::panic_str("ERR_OVERFLOW"));

        let collateral = self.config.collateral_token.clone();
        let memo = format!("notch:claim:{market_id}");

        self.markets.insert(market_id.clone(), market);
        self.positions.insert(key, position);
        self.markets.flush();
        self.positions.flush();

        emit_event(
            "claim_requested",
            serde_json::json!({
                "market_id": market_id,
                "account_id": account_id,
                "amount": amount.to_string(),
            }),
        );

        ext_ft::ext(collateral)
            .with_static_gas(GAS_FOR_FT_TRANSFER)
            .with_attached_deposit(NearToken::from_yoctonear(1))
            .ft_transfer(account_id.clone(), U128(amount), Some(memo))
            .then(
                ext_self::ext(env::current_account_id())
                    .with_static_gas(GAS_FOR_CLAIM_CALLBACK)
                    .on_claim_transfer(market_id, account_id, U128(amount)),
            )
    }
}

// ---------------------------------------------------------------------------
// Validation, events and helper types used by the generated bindings
// ---------------------------------------------------------------------------

fn is_valid_market_id(id: &str) -> bool {
    is_valid_slug(id, MAX_MARKET_ID_LEN)
}

/// Identifier-like values: non-empty, bounded, ASCII alphanumeric plus
/// `-`, `_`, `.`. Used for market IDs, topic IDs, source IDs, projects and
/// metric names.
fn is_valid_slug(value: &str, max_len: usize) -> bool {
    !value.is_empty()
        && value.len() <= max_len
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.'))
}

/// Validates battle-specific configuration. Returns a stable error code that
/// is panicked by `create_market`, keeping rejected creation atomic.
fn validate_battle_config(
    config: &BattleConfigArgs,
    market_source_id: &str,
    resolve_after: u64,
) -> Result<(), &'static str> {
    validate_battle_topic(&config.topic_a)?;
    validate_battle_topic(&config.topic_b)?;

    if config.topic_a.topic_id == config.topic_b.topic_id
        || config.topic_a.article_title == config.topic_b.article_title
    {
        return Err("ERR_TOPICS_NOT_DISTINCT");
    }

    // A battle is only meaningful when both topics come from the same source,
    // project and metric. The shared observation window is a single stored
    // field, so both sides necessarily use the same window.
    if config.topic_a.source_id != config.topic_b.source_id
        || config.topic_a.project != config.topic_b.project
        || config.topic_a.metric != config.topic_b.metric
    {
        return Err("ERR_INCOMPATIBLE_TOPICS");
    }

    if config.topic_a.source_id != market_source_id {
        return Err("ERR_SOURCE_MISMATCH");
    }

    if config.observation_start.0 >= config.observation_end.0 {
        return Err("ERR_INVALID_OBSERVATION_WINDOW");
    }
    // A market cannot become resolvable before the shared observation window
    // ends. Replay markets use a historical window, which satisfies this.
    if config.observation_end.0 > resolve_after {
        return Err("ERR_OBSERVATION_AFTER_RESOLVE");
    }
    if config.min_baseline_views.0 == 0 {
        return Err("ERR_INVALID_MIN_BASELINE");
    }
    if config.tie_tolerance_bps > MAX_TIE_TOLERANCE_BPS {
        return Err("ERR_INVALID_TIE_TOLERANCE");
    }
    if config.tie_policy != TiePolicy::Void {
        return Err("ERR_INVALID_TIE_POLICY");
    }
    if config.formula != BattleFormula::GrowthComparisonV1 {
        return Err("ERR_INVALID_BATTLE_FORMULA");
    }

    Ok(())
}

fn validate_battle_topic(topic: &BattleTopic) -> Result<(), &'static str> {
    if !is_valid_slug(&topic.topic_id, MAX_TOPIC_ID_LEN) {
        return Err("ERR_INVALID_TOPIC_ID");
    }
    if !is_valid_slug(&topic.source_id, MAX_TOPIC_ID_LEN) {
        return Err("ERR_INVALID_TOPIC_SOURCE");
    }
    if !is_valid_slug(&topic.project, MAX_PROJECT_LEN) {
        return Err("ERR_INVALID_PROJECT");
    }
    if !is_valid_title(&topic.article_title, MAX_ARTICLE_TITLE_LEN) {
        return Err("ERR_INVALID_ARTICLE_TITLE");
    }
    if !is_valid_slug(&topic.metric, MAX_METRIC_LEN) {
        return Err("ERR_INVALID_METRIC");
    }
    Ok(())
}

fn is_valid_title(value: &str, max_len: usize) -> bool {
    !value.trim().is_empty() && value.len() <= max_len && !value.chars().any(|c| c.is_control())
}

fn is_valid_text(value: &str, max_len: usize) -> bool {
    !value.trim().is_empty() && value.len() <= max_len
}

/// Frozen rule/evidence/reason digests are committed as
/// `sha256:<64 hex characters>`.
fn is_valid_digest(value: &str) -> bool {
    let Some(hex) = value.strip_prefix("sha256:") else {
        return false;
    };
    hex.len() == 64 && hex.bytes().all(|b| b.is_ascii_hexdigit())
}

fn emit_event(event: &str, data: serde_json::Value) {
    let payload = serde_json::json!({
        "standard": "notch-market",
        "version": "1.0.0",
        "event": event,
        "data": data,
    });
    env::log_str(&format!("EVENT_JSON:{payload}"));
}

fn emit_entry_rejected(market_id: Option<&str>, sender_id: &AccountId, amount: u128, reason: &str) {
    emit_event(
        "entry_rejected",
        serde_json::json!({
            "market_id": market_id,
            "sender_id": sender_id,
            "amount": amount.to_string(),
            "reason": reason,
            "refunded": true,
        }),
    );
}

#[cfg(test)]
mod tests;
