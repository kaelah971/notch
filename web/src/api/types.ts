// Types mirror docs/FRONTEND_INTEGRATION_CONTRACT.md (S6). Amounts are base-unit strings.

export interface Envelope<T, M = Record<string, unknown>> { data: T; meta?: M }
export interface ApiErrorBody { error: { code: string; message: string; details?: unknown } }

export type DisplayStatus =
  | 'open_future' | 'closed' | 'resolved' | 'voided'
  | 'historical_replay_open' | 'historical_replay_closed' | 'historical_replay_resolved'

export type MarketMode = 'trend_trading' | 'trend_battle'

export interface BattleTopic { topic_id: string; source_id: string; project: string; article_title: string; metric: string }
export interface BattleSpec {
  topic_a: BattleTopic; topic_b: BattleTopic
  observation_start: string; observation_end: string
  formula: string; min_baseline_views: string; tie_tolerance_bps: number; tie_policy: string
}

export interface Market {
  market_id: string
  mode: MarketMode
  question: string
  choices: string[]
  source_id: string
  rule_hash: string
  status: string
  display_status: DisplayStatus
  is_historical_replay: boolean
  is_future_prediction: boolean
  entries_open: boolean
  entries_paused: boolean
  open_at_utc: string
  close_at_utc: string
  resolve_after_utc: string
  totals: string[]
  escrow_total: string
  paid_total: string
  winning_outcome: number | null
  winning_choice: string | null
  evidence_hash: string | null
  resolution_kind: string | null
  created_at_utc: string
  resolved_at_utc: string | null
  battle: BattleSpec | null
  rule_available: boolean
  evidence_available: boolean
}

export interface MarketDetail extends Market {
  onchain?: unknown
  totals_view?: unknown
  contract_config?: { collateral_token?: string; min_entry_amount?: string; [k: string]: unknown }
  rule?: Record<string, unknown> | null
  rule_record?: Record<string, unknown> | null
  evidence_digest?: unknown
  evidence_verified?: boolean
}

export interface MarketEvidence {
  rule?: Record<string, unknown> | null
  evidence: Record<string, unknown> | null
  evidence_available: boolean
  verified: boolean
  [k: string]: unknown
}

export type BriefStatus = 'AI_GENERATED' | 'NON_AI_FALLBACK' | 'INVALID_AI_FALLBACK' | 'AI_UNAVAILABLE_FALLBACK'

export interface Brief {
  brief_id: string
  brief_type: string
  topic: string
  generation_status: BriefStatus
  provider: string
  model: string
  headline: string
  evidence_references: unknown[]
  [k: string]: unknown
}

export interface Trend {
  candidate_id: string
  canonical_topic_id: string
  title: string
  category: string
  eligibility_status: string
  score: number
  observed_at: string
  source_count: number
  sources: string[]
  source_urls: string[]
  settlement_coverage?: { window_start: string; window_end: string; latest_views: number; latest_date: string }
}

export type PulseWindow = '24h' | '7d' | '30d' | 'all'
export interface PulseCoverage {
  available: boolean
  status: 'not_started' | 'tracking' | 'degraded' | 'not_configured' | string
  source: string
  scope: string
  historical_backfill: boolean
  started_at_utc: string | null
  start_block_height: number | null
  last_scanned_block_height: number | null
  last_scanned_at_utc: string | null
  latest_final_block_height: number | null
  latest_final_at_utc: string | null
  indexed_event_count: number
  last_error: string | null
  limitations: string[]
}
export interface PulseCall {
  event_id: string
  tx_hash: string
  receipt_id: string
  log_index: number
  market_id: string
  account_id: string
  outcome: number
  amount_base_units: string
  block_height: number
  block_hash: string
  observed_at_utc: string
  source: string
  verification: string
}
export interface PulseHotMarket {
  market_id: string
  confirmed_volume_base_units: string
  successful_entries: number
  successful_entry_events: number
  forecaster_count: number
  last_activity_at_utc: string
}
export interface PulseData {
  coverage: PulseCoverage
  as_of_utc: string | null
  window: PulseWindow
  currency: { symbol: string; decimals: number; unit: string }
  metrics: {
    forecaster_count: number
    new_forecaster_count: number
    confirmed_volume_base_units: string
    successful_entries: number
    successful_entry_events: number
  }
  hot_markets: PulseHotMarket[]
  recent_calls: PulseCall[]
}

export interface EntryIntent {
  network: string
  signer: string
  receiver: string
  method: string
  args: { receiver_id: string; amount: string; msg: string }
  attached_deposit_yocto: string
  gas_tgas: number
  market_id: string
  outcome: number
  choice: string
  stake: string
  collateral_token: string
  min_entry_amount: string
  signed: false
  broadcast: false
}

export interface Readiness {
  account: string; balance: string; decimals: number
  storage_registered: boolean; storage_total: string | null
  min_market_entry: string; ready: boolean; blocker: string | null
}

export interface TokenBalance {
  asset_id: string; contract: string; symbol: string; decimals: number
  balance: string; storage_registered: boolean; storage_total: string | null; name: string
}
export interface WalletBalances {
  account_id: string
  network: string
  near: { yocto_near: string; decimals: number }
  tokens: TokenBalance[]
  collateral: { contract: string; decimals: number; balance: string; storage_registered: boolean; min_entry_amount: string; ready: boolean }
}

export type ClaimState = 'open' | 'pending' | 'claimable' | 'claimed' | 'not_eligible'
export type PredictionStatus = 'PENDING' | 'CORRECT' | 'INCORRECT' | 'VOIDED' | 'UNKNOWN'
export interface Position {
  market_id: string
  mode: MarketMode
  question: string
  market_status: string
  winning_choice: string | null
  stakes: string[]
  total_stake: string
  claimed_total: string
  pending_amount: string
  claimable: string
  claim_state: ClaimState
  prediction_status: PredictionStatus
  prediction_choice: string | null
  prediction_choices: string[]
  evidence_hash: string | null
  resolution_kind: string | null
}

export interface FundingAsset { asset_id: string; decimals: number; blockchain: string; symbol: string; contract_address?: string }
export interface FundingTokens {
  tokens: FundingAsset[]
  routes: { source: FundingAsset; destination: FundingAsset; label: string }[]
  destination_asset: string
}
export interface QuoteRequest {
  source_asset: string; amount: string; recipient: string; refund_to: string
  deposit_type: 'INTENTS' | 'ORIGIN_CHAIN'; slippage_bps: number; deadline_minutes: number; dry: boolean
}
export interface FundingStep {
  step: number; action: string; contract: string; method: string
  args: Record<string, unknown>; attached_deposit_yocto: string; gas_tgas: number; note?: string
}
export interface FundingInstructions {
  supported: boolean; blocker: string | null; deposit_type: string
  provider_deposit_address: string | null; deadline: string
  steps: FundingStep[]; warnings: string[]
}
export interface FundingQuote {
  quote_id: string
  state: string
  dry: boolean
  source_asset: string; source_symbol: string; source_decimals: number
  destination_symbol: string; destination_decimals: number
  amount_in: string; amount_out: string; min_amount_out: string
  deposit_type: string
  deposit_address: string | null
  deposit_memo: string | null
  deadline: string
  expires_at: string
  provider_status: string | null
  balance_verified: boolean
  balance_delta: string | null
  last_error: string | null
  deposit_submitted: boolean
}

/** A pool-totals value the S6 API actually read from the contract, at NEAR block time. */
export interface PoolSnapshot { block_ts_ns: string; observed_at_utc: string; totals: string[]; status: string }
