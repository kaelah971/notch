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

export interface BriefClaim {
  text: string
  kind: 'FACT' | 'INTERPRETATION' | 'UNKNOWN' | string
  evidence_refs: string[]
}

export interface BriefEvidenceReference {
  ref_id: string
  source: string
  title: string
  url?: string | null
  observed_at?: string | null
  raw_hash?: string | null
  kind?: string
}

export interface BriefInference {
  status?: 'LIVE_AI_VERIFIED' | 'DETERMINISTIC_FALLBACK' | 'UNAVAILABLE' | string
  provider: string
  model: string
  provider_base_url?: string
  response_model?: string
  request_timestamp?: string
  input_observation_cutoff?: string | null
  input_digest?: string
  input_evidence_digest?: string | null
  source_ids: string[]
  generation_status: BriefStatus | string
  request_id?: string
  verification?: { status: 'verified' | 'unverified' | 'unavailable' | 'not_applicable' | string; reason?: string }
}

export interface BriefResearch {
  supporting_up: BriefClaim[]
  supporting_down: BriefClaim[]
  key_assumptions: BriefClaim[]
  historical_context: BriefClaim[]
}

export interface Brief {
  brief_id: string
  brief_type: string
  topic: string
  generation_status: BriefStatus
  provider: string
  model: string
  headline: string
  summary?: string
  evidence_references: BriefEvidenceReference[]
  observed_signals?: BriefClaim[]
  notable_changes?: BriefClaim[]
  uncertainty?: BriefClaim[]
  missing_evidence?: string[]
  suggested_research_questions?: string[]
  measurement_window?: Record<string, unknown>
  data_as_of?: string
  resolution?: Record<string, unknown> | null
  fallback_reason?: string | null
  research?: BriefResearch
  inference?: BriefInference
  [k: string]: unknown
}

export type CouncilGenerationStatus = BriefStatus | 'MIXED_AI_AND_FALLBACK' | 'DETERMINISTIC_EVIDENCE_LENSES' | string

export interface CouncilClaim {
  text: string
  kind: 'FACT' | 'INTERPRETATION' | 'UNKNOWN' | string
  evidence_refs: string[]
}

export interface CouncilCitationValidation {
  status: 'valid' | 'invalid' | string
  checked_claims: number
  invalid_refs: string[]
  issues: string[]
}

export interface CouncilRole {
  role_id: 'bull_analyst' | 'bear_analyst' | 'evidence_verifier' | string
  label: string
  stance: 'UP' | 'DOWN' | 'NEUTRAL' | string
  position: 'UP' | 'DOWN' | 'NEUTRAL' | string
  headline: string
  thesis: string
  claims: CouncilClaim[]
  counterpoints: CouncilClaim[]
  open_questions: string[]
  generation_status: CouncilGenerationStatus
  provider: string
  model: string
  generated_at: string
  fallback_reason?: string | null
  snapshot_id: string
  input_digest: string
  citation_validation: CouncilCitationValidation
  inference?: BriefInference
}

export interface CouncilSnapshot {
  snapshot_id: string
  snapshot_digest: string
  input_digest: string
  market_id: string
  topic: string
  data_as_of: string
  measurement_window: Record<string, unknown>
  source_ids: string[]
  evidence_references: BriefEvidenceReference[]
  scope: Record<string, unknown>
  grounding_digest: string
}

export interface CouncilDisagreement {
  status: 'MIXED_EVIDENCE' | 'UP_ONLY' | 'DOWN_ONLY' | 'UNRESOLVED' | string
  summary: string
  records: Array<Record<string, unknown>>
  limitations: string[]
}

export interface CouncilAudit {
  audit_id: string
  event: string
  market_id: string
  occurred_at: string
  snapshot_id: string
  snapshot_digest: string
  input_digest: string
  source_ids: string[]
  roles: Array<Record<string, unknown>>
  disagreement_status: string
  ai_call_triggered: boolean
  request_id?: string | null
  result_digest: string
  execution_boundary: Record<string, boolean>
}

export interface ResearchCouncil {
  schema_version: string
  council_id: string
  market_id: string
  topic: string
  created_at: string
  generation_mode: CouncilGenerationStatus
  inference_status?: 'LIVE_AI_VERIFIED' | 'DETERMINISTIC_FALLBACK' | 'UNAVAILABLE' | string
  inference?: {
    status: string
    provider: string
    provider_base_url?: string | null
    model: string
    request_id?: string | null
    call_count: number
    role_generation: string
    independent_role_calls: boolean
    [k: string]: unknown
  }
  ai_call_triggered: boolean
  cache_hit: boolean
  snapshot: CouncilSnapshot
  roles: CouncilRole[]
  disagreement: CouncilDisagreement
  audit: CouncilAudit
  result_digest: string
  limitations: string[]
  execution: Record<string, boolean>
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

export type ScoutDirection = 'all' | 'rising' | 'falling'
export interface ScoutObservation { date: string; views: number; observation_id: string }
export interface ScoutCandidate {
  candidate_id: string
  canonical_topic_id: string
  topic: string
  source_article: string
  source_url: string
  source: { id: string; project: string; access: string; agent: string; metric: string; article: string; article_url: string; api_url: string | null }
  observation_window: { start: string | null; end: string | null; sample_count: number; expected_days: number; missing_days: string[]; minimum_sample_days: number }
  baseline: { date: string; views: number } | null
  current: { date: string; views: number } | null
  change: { change_bps: number | null; change_percent: number | null; absolute_views: number | null; formula: string }
  direction: 'RISING' | 'FALLING' | 'STABLE'
  is_notable: boolean
  is_unusual: boolean
  freshness: { observed_at: string | null; age_hours: number | null; stale_after_hours: number; status: string }
  evidence_digest: string
  evidence: { daily: ScoutObservation[]; raw_hashes: string[] }
  existing_market_match: { market_id: string; status: string; rule_hash?: string; question?: string; topics: string[] } | null
  candidate_status: 'REVIEWABLE' | 'NEEDS_REVIEW' | 'STALE' | 'UNAVAILABLE'
  uncertainty: string[]
  limitations: string[]
  rank: { score: number; version: string; components: Record<string, number> }
  proposal: { proposal_id: string; status: string; published: false; human_review_required: true; topic: string; question: string; direction: string; threshold_bps: number; evidence_digest: string; review_note: string; [k: string]: unknown } | null
}
export interface ScoutMeta {
  count: number
  direction: string
  status: string
  version: string
  supported_topics: string[]
  source: string
  formula: string
  notable_change_bps: number
  unusual_change_bps: number
  minimum_sample_days: number
  minimum_baseline_views: number
  stale_after_hours: number
  ranking: string
  source_mode: string
  reason?: string
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
export interface PulseParticipant {
  account_id: string
  confirmed_volume_base_units: string
  successful_entries: number
  successful_entry_events: number
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
  participants: PulseParticipant[]
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

export interface FundingAsset {
  asset_id: string; decimals: number; blockchain: string; symbol: string
  contract_address?: string; price?: number; price_updated_at?: string | null
}
export interface FundingRoute { source: FundingAsset; destination: FundingAsset; label: string }
export interface FundingTokens {
  tokens: FundingAsset[]
  routes: FundingRoute[]
  destination_asset: string
  destination_chain: string
  source_chains: string[]
  network: string
  provider: string
  observed_at: string | null
}
export interface MainnetFundingDiscovery {
  provider: string; provider_id: string; network: string; environment: string
  tokens: FundingAsset[]; source_tokens: FundingAsset[]; destination_candidates: FundingAsset[]
  routes: FundingRoute[]; source_chains: string[]; destination_asset: string | null
  recipient: string | null; quote_enabled: boolean; quote_mode: 'dry_only' | 'unavailable' | string
  auth_mode: string; auth_configured: boolean; credentials_exposed: false
  fee_notice: string; execution_supported: false; execution_reasons: string[]
  unavailable_reasons: string[]; signature_public_key_id: string; observed_at: string | null
}
export interface QuoteRequest {
  source_asset: string; source_chain?: string; amount: string; recipient: string; refund_to: string
  deposit_type: 'INTENTS' | 'ORIGIN_CHAIN'; slippage_bps: number; deadline_minutes: number; dry: boolean
}
export interface FundingStep {
  step: number; action: string; contract: string; method: string
  args: Record<string, unknown>; attached_deposit_yocto: string; gas_tgas: number; note?: string
}
export interface FundingInstructions {
  supported: boolean; blocker: string | null; manual_only?: boolean; deposit_type: string
  source_chain?: string; source_asset?: string; source_symbol?: string; source_decimals?: number
  destination_asset?: string; destination_symbol?: string; destination_decimals?: number
  amount_in?: string; min_amount_out?: string; deposit_memo?: string | null
  recipient?: string; refund_to?: string; deadline: string | null
  provider_deposit_address: string | null
  steps: FundingStep[]; warnings: string[]
}
export interface FundingQuote {
  quote_id: string
  correlation_id?: string
  state: string
  dry: boolean
  source_asset: string; source_symbol: string; source_chain: string; source_decimals: number
  destination_asset?: string; destination_symbol: string; destination_decimals: number
  amount_in: string; amount_out: string; min_amount_out: string
  deposit_type: string; refund_type?: string; recipient?: string; refund_to?: string
  deposit_address: string | null
  deposit_memo: string | null
  deadline: string
  expires_at: string
  quote_timestamp?: string
  slippage_bps?: number
  provider_status: string | null
  balance_verified: boolean
  balance_delta: string | null
  last_error: string | null
  deposit_submitted: boolean
  deposit_tx_hash?: string | null
  signature_verified?: boolean
  provider_result?: string | null
  settlement_evidence?: FundingSettlementEvidence
  destination_verification?: FundingDestinationVerification
}
export interface ProviderQuoteDetails {
  amount_in: string; amount_in_formatted: string; amount_in_usd: string
  min_amount_in: string; amount_out: string; amount_out_formatted: string; amount_out_usd: string
  min_amount_out: string; time_estimate: number
  deposit_address?: string | null; deposit_memo?: string | null
  refund_fee?: string | null; withdraw_fee?: string | null
  time_when_inactive?: string | null; deadline?: string | null
}
export interface FundingQuoteValidation {
  route: FundingRoute
  expires_at: string
  implied_fee_usd: string
  warnings: string[]
  signature_verified?: boolean
}
export interface FundingTransactionReference { hash: string; explorer_url?: string }
export interface FundingSettlementEvidence {
  provider_status: string | null; updated_at: string | null
  intent_hashes: string[]; near_tx_hashes: string[]
  origin_chain_tx_hashes: FundingTransactionReference[]
  destination_chain_tx_hashes: FundingTransactionReference[]
  refund_reason: string | null; refunded_amount: string | null; amount_out?: string | null
}
export interface FundingDestinationVerification {
  state: 'PROVIDER_SUCCESS' | 'DESTINATION_VERIFIED' | 'DESTINATION_VERIFICATION_PENDING' | string | null
  account: string; asset_id: string; balance_before: string | null; balance_after: string | null
  balance_delta: string | null; required_min_amount_out: string; verified: boolean; error: string | null
}
export interface FundingQuoteResult {
  quote: FundingQuote
  provider_quote: { correlation_id: string; timestamp: string; signature?: string; quote_request: Record<string, unknown>; quote: ProviderQuoteDetails }
  validation: FundingQuoteValidation
  instructions?: FundingInstructions | null
}

export type CreatorNoteStatus = 'DRAFT' | 'PUBLISHED' | 'WITHDRAWN'
export type CreatorNotePosition = 'UP' | 'DOWN' | 'NEUTRAL'
export interface CreatorNoteEvidence {
  source_id: string
  url: string
  observed_at: string
  claim: string
}
export interface CreatorNoteReference { kind: 'market' | 'topic'; id: string; label: string }
export interface CreatorNoteStrategyReference { id: string; revision_hash: string; integrity: 'as_supplied' | string }
export interface CreatorNoteEvaluationReference { id: string; result_digest: string; integrity: 'as_supplied' | string }
export interface CreatorNoteRevision {
  revision: number
  status: CreatorNoteStatus
  content_digest: string
  evidence_digest: string
  created_at: string
}
export interface CreatorPremiumOffer {
  enabled: boolean
  price_base_units: string | null
  token_contract: string | null
  token_symbol: string | null
  token_decimals: number | null
  body_digest: string | null
  locked: boolean
  body?: string | null
}
export interface CreatorPayoutStatus {
  configured: boolean
  creator_account: string
  network: string
  token_contract: string | null
  payout_account: string | null
  token_symbol: string | null
  token_decimals: number | null
  storage_registered: boolean
  verified_at: string | null
}
export interface CreatorSubscriptionPlanScope {
  note_id: string
  title?: string
  revision?: number
  content_digest?: string
  premium?: CreatorPremiumOffer
  available?: boolean
}
export interface CreatorSubscriptionPlanVersion {
  version: number
  title: string
  description: string
  duration_days: number
  price_base_units: string
  token_symbol: string
  token_decimals: number
  scope_note_ids: string[]
  created_at: string
}
export interface CreatorSubscriptionPlan {
  plan_id: string
  creator_account: string
  status: 'ACTIVE' | 'INACTIVE' | string
  terms_version: number
  title: string
  description: string
  duration_days: 7 | 30 | number
  price_base_units: string
  token_contract: string
  token_symbol: string
  token_decimals: number
  scope: CreatorSubscriptionPlanScope[]
  scope_note_ids?: string[]
  subscriber_count: number
  created_at: string
  updated_at: string
  version_history?: CreatorSubscriptionPlanVersion[]
}
export interface CreatorSubscriptionPayment {
  payment_id: string
  payment_intent_id: string
  plan_version: number
  amount_base_units: string
  token_contract: string
  term_started_at: string
  term_expires_at: string
  granted_at: string
  tx_hash: string
  receipt_id: string
  explorer_url: string
}
export interface CreatorSubscription {
  subscription_id: string
  subscriber_account: string
  creator_account: string
  plan_id: string
  plan_title: string
  status: 'ACTIVE' | 'EXPIRED' | 'CANCELLED' | 'PAYMENT_PENDING' | 'PAYMENT_FAILED' | 'PENDING' | string
  access_active: boolean
  renewal_cancelled: boolean
  renewal_available: boolean
  plan_version: number | null
  duration_days: number
  price_base_units: string | null
  token_symbol: string | null
  token_contract: string | null
  scope: CreatorSubscriptionPlanScope[]
  started_at: string | null
  expires_at: string | null
  latest_payment_status: string | null
  latest_payment_intent_id: string | null
  last_tx_hash: string | null
  payments: CreatorSubscriptionPayment[]
  updated_at: string
}
export interface CreatorSubscriptions {
  subscriber_subscriptions: CreatorSubscription[]
  creator_subscriptions: CreatorSubscription[]
}
export interface CreatorPaymentAction {
  receiver_id: string
  method_name: 'ft_transfer' | string
  args: { receiver_id: string; amount: string; memo: string }
  gas_tgas: number
  attached_deposit_yocto: string
}
export interface CreatorEntitlement {
  entitlement_id: string
  intent_id: string
  buyer_account: string
  creator_account: string
  note_id: string
  note_revision: number
  content_digest: string
  tx_hash: string
  receipt_id: string
  granted_at: string
  amount_base_units: string | null
  token_contract: string | null
  token_symbol: string | null
  recipient_account: string | null
  memo: string | null
  explorer_url: string
}
export interface CreatorPaymentIntent {
  intent_id: string
  payment_kind?: 'ONE_TIME' | 'SUBSCRIPTION' | string
  status: 'PENDING' | 'VERIFIED' | 'FAILED' | 'EXPIRED' | string
  buyer_account: string
  creator_account: string
  note_id: string
  note_title: string
  note_revision: number
  content_digest: string
  plan_id?: string | null
  plan_version?: number | null
  subscription_id?: string | null
  correlation_id?: string | null
  terms?: Record<string, unknown> | null
  network: 'testnet' | string
  token_contract: string
  token_symbol: string
  token_decimals: number
  amount_base_units: string
  recipient_account: string
  memo: string
  created_at: string
  expires_at: string
  updated_at: string
  tx_hash: string | null
  receipt_id: string | null
  explorer_url?: string
  failure_code: string | null
  failure_message: string | null
  action: CreatorPaymentAction
  disclosure: { testnet_only: boolean; refund_policy: string; user_approval_required: boolean; notch_signs_or_broadcasts: boolean }
  entitlement?: CreatorEntitlement
  subscription?: CreatorSubscription
  already_entitled?: boolean
}
export interface CreatorPremiumContent {
  note_id: string
  revision: number
  content_digest: string
  premium: { body: string; body_digest: string | null; price_base_units: string | null; token_contract: string | null; token_symbol: string | null; token_decimals: number | null }
  entitlement: CreatorEntitlement | null
  subscription?: CreatorSubscription | null
  access: 'creator' | 'purchased_revision' | 'subscription' | string
}
export interface CreatorPurchases {
  buyer_entitlements: CreatorEntitlement[]
  creator_sales: CreatorEntitlement[]
}
export interface CreatorResearchNote {
  schema: string
  note_id: string
  creator_account: string
  creator_verified: boolean
  status: CreatorNoteStatus
  revision: number
  title: string
  thesis: string
  reference: CreatorNoteReference
  position: CreatorNotePosition
  supporting_evidence: CreatorNoteEvidence[]
  contradictory_evidence: CreatorNoteEvidence[]
  observation_cutoff: string
  source_ids: string[]
  source_urls: string[]
  strategy_reference: CreatorNoteStrategyReference | null
  evaluation_reference: CreatorNoteEvaluationReference | null
  content_digest: string
  evidence_digest: string
  created_at: string
  updated_at: string
  published_at: string | null
  withdrawn_at: string | null
  withdrawal_reason: string | null
  premium: CreatorPremiumOffer
  revision_history?: CreatorNoteRevision[]
}
export interface PrivateResearchRecord {
  schema: string
  research_id: string
  owner_account: string
  visibility: 'PRIVATE' | string
  market_id: string | null
  title: string
  thesis: string
  predicted_outcome: string
  confidence: number | null
  source_references: string[]
  invalidation_condition: string
  created_at: string
  updated_at: string
  market: {
    market_id: string
    question: string | null
    status: string | null
    winning_choice?: string | null
    entries_open?: boolean | null
    close_at?: string | null
    resolve_after?: string | null
    resolved_at?: string | null
  } | null
}
export interface CreatorNoteChallenge {
  challenge_id: string
  account_id: string
  nonce_b64: string
  message: string
  recipient: string
  created_at: string
  expires_at: string
}
export interface CreatorIdentitySession {
  account_id: string
  public_key: string
  verified: boolean
  network?: string
  verification_method: string
  session_token: string
  session_expires_at: string
}
export interface CreatorNotesMeta { count: number; status?: string; private?: boolean; creator_account?: string }
export type FundingStatusResult = FundingQuote & {
  provider_result?: string | null
  settlement_evidence?: FundingSettlementEvidence
  destination_verification?: FundingDestinationVerification
  events?: Array<{ event: string; created_at: string; data: Record<string, unknown> }>
  amount_in_display?: string; amount_out_display?: string; min_amount_out_display?: string
}

/** A pool-totals value the S6 API actually read from the contract, at NEAR block time. */
export interface PoolSnapshot { block_ts_ns: string; observed_at_utc: string; totals: string[]; status: string }
