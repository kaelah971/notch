import {
  canonicalStrategyHash,
  evaluateStrategy,
  type StrategyDefinition,
  type StrategyEvaluation,
} from '../strategy/strategy.ts'
import type { HistoricalDataset } from '../practice/backtest.ts'
import type { Market, MarketDetail } from '../api/types.ts'

export const AUTOPILOT_SCHEMA_VERSION = 'notch.autopilot/1'
export const AUTOPILOT_POLICY_VERSION = 'notch.autopilot-policy/1'
export const AUTOPILOT_STORAGE_KEY = 'notch.autopilot.v1'
export const AUTOPILOT_DEFAULT_RISK: AutopilotRiskConfig = {
  budget_credits: 1_000,
  stake_mode: 'PERCENTAGE',
  stake_value: 10,
  max_exposure_credits: 250,
  max_positions: 1,
  daily_loss_limit_credits: 100,
  cooldown_seconds: 900,
}

export type AutopilotStatus = 'ACTIVE' | 'PAUSED' | 'STOPPED'
export type AutopilotMode = 'MANUAL_REVIEW' | 'PAPER_AUTO'
export type AutopilotRunMode = 'FORWARD_EVALUATION' | 'HISTORICAL_SIMULATION'
export type AutopilotActionStatus =
  | 'PAPER_ENTRY_APPROVED'
  | 'NEEDS_MANUAL_REVIEW'
  | 'BLOCKED_BY_RISK'
  | 'MARKET_INELIGIBLE'
  | 'INSUFFICIENT_EVIDENCE'
  | 'COOLDOWN'
  | 'ALREADY_PROCESSED'
  | 'PAUSED'
export type AutopilotReasonCode =
  | 'NO_MARKETS_RETURNED'
  | 'MARKET_DATA_UNAVAILABLE'
  | 'RULE_UNAVAILABLE'
  | 'RULE_HASH_MISMATCH'
  | 'SOURCE_MISMATCH'
  | 'TOPIC_MISMATCH'
  | 'METHODOLOGY_MISMATCH'
  | 'WINDOW_UNVERIFIABLE'
  | 'WINDOW_MISMATCH'
  | 'RESOLUTION_MISMATCH'
  | 'HISTORICAL_REPLAY'
  | 'MARKET_NOT_OPEN'
  | 'ENTRY_PAUSED'
  | 'DEADLINE_PASSED'
  | 'DEADLINE_UNAVAILABLE'
  | 'STALE_EVIDENCE'
  | 'MISSING_EVIDENCE'
  | 'ZERO_BASELINE'
  | 'NO_SIGNAL'
  | 'POLICY_PAUSED'
  | 'POLICY_STOPPED'
  | 'COOLDOWN'
  | 'DAILY_LOSS_LIMIT'
  | 'MAX_POSITIONS'
  | 'MAX_EXPOSURE'
  | 'BUDGET_EXHAUSTED'
  | 'ALREADY_PROCESSED'
  | 'MANUAL_REVIEW_REQUIRED'
  | 'PAPER_POLICY_ALLOWED'

export interface AutopilotRiskConfig {
  budget_credits: number
  stake_mode: 'FIXED' | 'PERCENTAGE'
  stake_value: number
  max_exposure_credits: number
  max_positions: number
  daily_loss_limit_credits: number
  cooldown_seconds: number
}

export interface AutopilotPolicy {
  policy_id: string
  schema_version: typeof AUTOPILOT_POLICY_VERSION
  version: number
  strategy_id: string
  strategy_hash: string
  status: AutopilotStatus
  mode: AutopilotMode
  risk: AutopilotRiskConfig
  created_at_utc: string
  updated_at_utc: string
}

export interface AutopilotAction {
  action_id: string
  idempotency_key: string
  policy_id: string
  policy_version: number
  strategy_id: string
  strategy_hash: string
  evidence_snapshot_id: string | null
  evidence_digest: string | null
  evidence_cutoff_utc: string | null
  market_id: string | null
  market_rule_hash: string | null
  market_status: string | null
  decision_cutoff_utc: string | null
  status: AutopilotActionStatus
  reason_code: AutopilotReasonCode
  explanation: string
  requested_stake: number
  stake: number
  exposure_before: number
  exposure_after: number
  active_positions_before: number
  daily_loss_before: number
  risk_config: AutopilotRiskConfig
  simulated_position_id: string | null
  run_timestamp_utc: string
  run_mode: AutopilotRunMode
  strategy_prediction: 'UP' | 'DOWN' | null
  signal_momentum_bps: number | null
  source_data_as_of: string | null
  manual_review_of: string | null
  settled_result: 'WIN' | 'LOSS' | 'VOID' | null
  settled_at_utc: string | null
}

export interface AutopilotState {
  version: 1
  policy: AutopilotPolicy | null
  actions: AutopilotAction[]
}

export interface AutopilotMarketAssessment {
  market_id: string
  market: Market | MarketDetail
  eligible: boolean
  reasons: Array<{ code: AutopilotReasonCode; explanation: string }>
  rule_hash: string | null
  topic: string | null
  checked_at_utc: string
}

export interface AutopilotLedgerSnapshot {
  current_exposure: number
  available_budget: number
  active_positions: number
  daily_loss: number
  last_action_at_utc: string | null
}

export interface AutopilotEvaluationResult {
  state: AutopilotState
  run_id: string
  run_timestamp_utc: string
  run_mode: AutopilotRunMode
  strategy_evaluation: StrategyEvaluation
  market_assessments: AutopilotMarketAssessment[]
  actions: AutopilotAction[]
  eligible_market_count: number
  ledger: AutopilotLedgerSnapshot
  no_eligible_market_reason: string | null
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>
type AutopilotMarket = Market | MarketDetail

function stableHash(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function hashLabel(value: unknown): string { return `fnv1a32:${stableHash(JSON.stringify(value))}` }
function browserStorage(): StorageLike | null {
  if (typeof window === 'undefined') return null
  try { return window.localStorage } catch { return null }
}
function isRecord(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === 'object' && !Array.isArray(value)) }
function iso(value: string): string { return new Date(value).toISOString() }
function day(value: string): string { return value.slice(0, 10) }
function normalize(value: string): string { return value.toLowerCase().replace(/[^a-z0-9]+/g, '') }
function asString(value: unknown): string | null { return typeof value === 'string' && value ? value : null }
function asNumber(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) ? value : null }

export function emptyAutopilotState(): AutopilotState { return { version: 1, policy: null, actions: [] } }

export function validateAutopilotRisk(risk: AutopilotRiskConfig): string[] {
  const errors: string[] = []
  if (!Number.isSafeInteger(risk.budget_credits) || risk.budget_credits <= 0) errors.push('Virtual budget must be a positive whole number.')
  if (risk.stake_mode !== 'FIXED' && risk.stake_mode !== 'PERCENTAGE') errors.push('Stake mode must be fixed credits or a percentage.')
  if (!Number.isSafeInteger(risk.stake_value) || risk.stake_value <= 0 || (risk.stake_mode === 'PERCENTAGE' && risk.stake_value > 100)) errors.push('Stake value is outside the supported risk range.')
  if (risk.stake_mode === 'FIXED' && risk.stake_value > risk.budget_credits) errors.push('Fixed stake cannot exceed the virtual budget.')
  if (!Number.isSafeInteger(risk.max_exposure_credits) || risk.max_exposure_credits <= 0 || risk.max_exposure_credits > risk.budget_credits) errors.push('Maximum exposure must be within the virtual budget.')
  if (!Number.isSafeInteger(risk.max_positions) || risk.max_positions <= 0) errors.push('Maximum simultaneous positions must be at least one.')
  if (!Number.isSafeInteger(risk.daily_loss_limit_credits) || risk.daily_loss_limit_credits < 0 || risk.daily_loss_limit_credits > risk.budget_credits) errors.push('Daily loss limit must be between zero and the virtual budget.')
  if (!Number.isSafeInteger(risk.cooldown_seconds) || risk.cooldown_seconds < 0) errors.push('Cooldown must be a non-negative whole number of seconds.')
  return errors
}

function validRisk(value: unknown): value is AutopilotRiskConfig {
  if (!isRecord(value)) return false
  const risk = value as Partial<AutopilotRiskConfig>
  return typeof risk.budget_credits === 'number'
    && typeof risk.stake_mode === 'string'
    && typeof risk.stake_value === 'number'
    && typeof risk.max_exposure_credits === 'number'
    && typeof risk.max_positions === 'number'
    && typeof risk.daily_loss_limit_credits === 'number'
    && typeof risk.cooldown_seconds === 'number'
    && validateAutopilotRisk(risk as AutopilotRiskConfig).length === 0
}

function normalizePolicy(value: unknown): AutopilotPolicy | null {
  if (!isRecord(value) || !validRisk(value.risk)) return null
  const policy = value as Partial<AutopilotPolicy>
  const risk = policy.risk as AutopilotRiskConfig
  const policyVersion = policy.version
  if (typeof policy.policy_id !== 'string' || typeof policy.strategy_id !== 'string' || typeof policy.strategy_hash !== 'string') return null
  if (policy.schema_version !== AUTOPILOT_POLICY_VERSION || typeof policyVersion !== 'number' || !Number.isSafeInteger(policyVersion) || policyVersion < 1) return null
  if (!['ACTIVE', 'PAUSED', 'STOPPED'].includes(String(policy.status)) || !['MANUAL_REVIEW', 'PAPER_AUTO'].includes(String(policy.mode))) return null
  if (typeof policy.created_at_utc !== 'string' || typeof policy.updated_at_utc !== 'string') return null
  return {
    policy_id: policy.policy_id,
    schema_version: AUTOPILOT_POLICY_VERSION,
    version: policyVersion as number,
    strategy_id: policy.strategy_id,
    strategy_hash: policy.strategy_hash,
    status: policy.status as AutopilotStatus,
    mode: policy.mode as AutopilotMode,
    risk,
    created_at_utc: policy.created_at_utc,
    updated_at_utc: policy.updated_at_utc,
  }
}

function normalizeAction(value: unknown): AutopilotAction | null {
  if (!isRecord(value) || !validRisk(value.risk_config)) return null
  const action = value as Partial<AutopilotAction>
  const riskConfig = action.risk_config as AutopilotRiskConfig
  const policyVersion = action.policy_version
  const statuses: AutopilotActionStatus[] = ['PAPER_ENTRY_APPROVED', 'NEEDS_MANUAL_REVIEW', 'BLOCKED_BY_RISK', 'MARKET_INELIGIBLE', 'INSUFFICIENT_EVIDENCE', 'COOLDOWN', 'ALREADY_PROCESSED', 'PAUSED']
  if (typeof action.action_id !== 'string' || typeof action.idempotency_key !== 'string' || typeof action.policy_id !== 'string' || typeof action.strategy_id !== 'string' || typeof action.strategy_hash !== 'string') return null
  if (typeof policyVersion !== 'number' || !Number.isSafeInteger(policyVersion) || policyVersion < 1 || !statuses.includes(action.status as AutopilotActionStatus)) return null
  if (typeof action.reason_code !== 'string' || typeof action.explanation !== 'string' || typeof action.run_timestamp_utc !== 'string') return null
  if (!Number.isFinite(action.requested_stake) || !Number.isFinite(action.stake) || !Number.isFinite(action.exposure_before) || !Number.isFinite(action.exposure_after) || !Number.isFinite(action.active_positions_before) || !Number.isFinite(action.daily_loss_before)) return null
  return {
    action_id: action.action_id,
    idempotency_key: action.idempotency_key,
    policy_id: action.policy_id,
    policy_version: policyVersion as number,
    strategy_id: action.strategy_id,
    strategy_hash: action.strategy_hash,
    evidence_snapshot_id: asString(action.evidence_snapshot_id),
    evidence_digest: asString(action.evidence_digest),
    evidence_cutoff_utc: asString(action.evidence_cutoff_utc),
    market_id: asString(action.market_id),
    market_rule_hash: asString(action.market_rule_hash),
    market_status: asString(action.market_status),
    decision_cutoff_utc: asString(action.decision_cutoff_utc),
    status: action.status as AutopilotActionStatus,
    reason_code: action.reason_code as AutopilotReasonCode,
    explanation: action.explanation,
    requested_stake: action.requested_stake as number,
    stake: action.stake as number,
    exposure_before: action.exposure_before as number,
    exposure_after: action.exposure_after as number,
    active_positions_before: action.active_positions_before as number,
    daily_loss_before: action.daily_loss_before as number,
    risk_config: riskConfig,
    simulated_position_id: asString(action.simulated_position_id),
    run_timestamp_utc: action.run_timestamp_utc,
    run_mode: action.run_mode === 'HISTORICAL_SIMULATION' ? 'HISTORICAL_SIMULATION' : 'FORWARD_EVALUATION',
    strategy_prediction: action.strategy_prediction === 'UP' || action.strategy_prediction === 'DOWN' ? action.strategy_prediction : null,
    signal_momentum_bps: asNumber(action.signal_momentum_bps),
    source_data_as_of: asString(action.source_data_as_of),
    manual_review_of: asString(action.manual_review_of),
    settled_result: action.settled_result === 'WIN' || action.settled_result === 'LOSS' || action.settled_result === 'VOID' ? action.settled_result : null,
    settled_at_utc: asString(action.settled_at_utc),
  }
}

export function normalizeAutopilotState(value: unknown): AutopilotState {
  if (!isRecord(value) || value.version !== 1) return emptyAutopilotState()
  const actions = Array.isArray(value.actions) ? value.actions.map(normalizeAction).filter((action): action is AutopilotAction => Boolean(action)) : []
  return { version: 1, policy: normalizePolicy(value.policy), actions }
}

export function readAutopilotState(storage: StorageLike | null = browserStorage()): AutopilotState {
  if (!storage) return emptyAutopilotState()
  try { return normalizeAutopilotState(JSON.parse(storage.getItem(AUTOPILOT_STORAGE_KEY) ?? 'null')) } catch { return emptyAutopilotState() }
}

export function writeAutopilotState(state: AutopilotState, storage: StorageLike | null = browserStorage()): boolean {
  if (!storage) return false
  try { storage.setItem(AUTOPILOT_STORAGE_KEY, JSON.stringify(normalizeAutopilotState(state))) ; return true } catch { return false }
}

export function strategyAutopilotCompatibility(strategy: StrategyDefinition, dataset: HistoricalDataset): { ok: true } | { ok: false; reason: string } {
  if (strategy.source.id !== 'wikimedia-pageviews-v1' || strategy.source.methodology_version !== 'wikimedia-pageviews-v1') return { ok: false, reason: 'Autopilot V1 only supports the published Wikimedia Pageviews V1 source contract.' }
  const evaluation = evaluateStrategy(strategy, dataset)
  if (evaluation.status !== 'EVALUATED') return { ok: false, reason: evaluation.reason ?? 'The selected strategy has no supported genuine observation fixture.' }
  return { ok: true }
}

export function createPolicy(strategy: StrategyDefinition, risk: AutopilotRiskConfig, mode: AutopilotMode, now: string, existing: AutopilotPolicy | null = null): AutopilotPolicy {
  const errors = validateAutopilotRisk(risk)
  if (errors.length) throw new Error(errors.join(' '))
  const normalizedNow = iso(now)
  const strategyHash = canonicalStrategyHash(strategy)
  return {
    policy_id: existing?.policy_id ?? `autopilot_${stableHash(strategy.strategy_id)}`,
    schema_version: AUTOPILOT_POLICY_VERSION,
    version: existing ? existing.version + 1 : 1,
    strategy_id: strategy.strategy_id,
    strategy_hash: strategyHash,
    status: 'ACTIVE',
    mode,
    risk: { ...risk },
    created_at_utc: existing?.created_at_utc ?? normalizedNow,
    updated_at_utc: normalizedNow,
  }
}

export function setPolicyStatus(state: AutopilotState, status: AutopilotStatus, now: string): AutopilotState {
  if (!state.policy) return state
  return { ...state, policy: { ...state.policy, status, updated_at_utc: iso(now) } }
}

export function ledgerSnapshot(policy: AutopilotPolicy, actions: AutopilotAction[], now: string): AutopilotLedgerSnapshot {
  const policyActions = actions.filter((action) => action.policy_id === policy.policy_id && action.policy_version <= policy.version)
  const positions = policyActions.filter((action) => action.status === 'PAPER_ENTRY_APPROVED' && action.settled_result == null)
  const currentExposure = positions.reduce((sum, action) => sum + action.stake, 0)
  const dailyLoss = policyActions.filter((action) => action.settled_result === 'LOSS' && action.settled_at_utc && day(action.settled_at_utc) === day(now)).reduce((sum, action) => sum + action.stake, 0)
  const dated = policyActions.filter((action) => action.status !== 'ALREADY_PROCESSED').sort((a, b) => Date.parse(b.run_timestamp_utc) - Date.parse(a.run_timestamp_utc))
  return {
    current_exposure: currentExposure,
    available_budget: Math.max(0, policy.risk.budget_credits - currentExposure),
    active_positions: positions.length,
    daily_loss: dailyLoss,
    last_action_at_utc: dated[0]?.run_timestamp_utc ?? null,
  }
}

function stakeFor(risk: AutopilotRiskConfig): number {
  return risk.stake_mode === 'FIXED' ? risk.stake_value : Math.floor(risk.budget_credits * risk.stake_value / 100)
}

function ruleRecord(market: Market | MarketDetail): Record<string, unknown> | null {
  const detail = market as MarketDetail
  if (isRecord(detail.rule)) return detail.rule
  if (isRecord(detail.rule_record)) {
    if (isRecord(detail.rule_record.rule)) return detail.rule_record.rule
    return detail.rule_record
  }
  return null
}

function ruleSource(rule: Record<string, unknown>): Record<string, unknown> | null { return isRecord(rule.source) ? rule.source : null }
function ruleTopics(rule: Record<string, unknown>): Array<Record<string, unknown>> { return Array.isArray(rule.topics) ? rule.topics.filter(isRecord) : [] }
function ruleWindow(rule: Record<string, unknown>): Record<string, unknown> | null {
  if (isRecord(rule.strategy_window)) return rule.strategy_window
  if (isRecord(rule.observation_window)) return rule.observation_window
  if (isRecord(rule.strategy) && isRecord(rule.strategy.observation_window)) return rule.strategy.observation_window
  return null
}

export function assessMarketCompatibility(strategy: StrategyDefinition, market: AutopilotMarket, now: string): AutopilotMarketAssessment {
  const reasons: Array<{ code: AutopilotReasonCode; explanation: string }> = []
  const checkedAt = iso(now)
  const rule = ruleRecord(market)
  const source = rule ? ruleSource(rule) : null
  const topics = ruleTopics(rule ?? {})
  const topic = (topics[0]?.article_title ?? topics[0]?.topic_id ?? source?.article ?? null) as string | null
  const ruleHash = asString((market as Market).rule_hash) ?? asString(rule?.rule_hash)
  const add = (code: AutopilotReasonCode, explanation: string) => reasons.push({ code, explanation })

  if (market.is_historical_replay || market.display_status.startsWith('historical_replay')) add('HISTORICAL_REPLAY', 'Historical replay markets are not forward paper targets.')
  if (market.mode !== 'trend_trading') add('RESOLUTION_MISMATCH', 'This strategy predicts UP/DOWN, but the published market is not a two-outcome trend market.')
  if (market.source_id !== strategy.source.id) add('SOURCE_MISMATCH', `Market source ${market.source_id} does not match strategy source ${strategy.source.id}.`)
  if (market.choices.length !== 2 || normalize(market.choices[0] ?? '') !== 'up' || normalize(market.choices[1] ?? '') !== 'down') add('RESOLUTION_MISMATCH', 'Published choices must be exactly UP then DOWN for this strategy outcome semantics.')
  if (market.status !== 'open' || market.display_status !== 'open_future' || !market.entries_open) add('MARKET_NOT_OPEN', 'The authoritative market status is not open for future entries.')
  if (market.entries_paused) add('ENTRY_PAUSED', 'The authoritative market has paused entries.')
  const close = Date.parse(market.close_at_utc)
  if (!Number.isFinite(close)) add('DEADLINE_UNAVAILABLE', 'The authoritative entry deadline is unavailable.')
  else if (close <= Date.parse(checkedAt)) add('DEADLINE_PASSED', `The authoritative entry deadline passed at ${market.close_at_utc}.`)
  if (!rule) add('RULE_UNAVAILABLE', 'The published rule was not returned, so topic, methodology and resolution cannot be verified.')
  if (rule && ruleHash && asString(rule.rule_hash) && ruleHash !== rule.rule_hash) add('RULE_HASH_MISMATCH', 'The returned rule hash does not match the market hash.')
  if (rule && source?.id !== strategy.source.id) add('METHODOLOGY_MISMATCH', 'The published rule source identifier does not match the strategy source.')
  if (rule && source && (source.project !== strategy.source.project || source.access !== strategy.source.access || source.agent !== strategy.source.agent || source.metric !== strategy.source.metric)) add('METHODOLOGY_MISMATCH', 'The published rule source metadata does not match the Wikimedia strategy methodology.')
  if (rule && topic && normalize(topic) !== normalize(strategy.source.topic)) add('TOPIC_MISMATCH', `Published topic ${topic} does not match strategy topic ${strategy.source.topic}.`)
  if (rule && !topic) add('TOPIC_MISMATCH', 'The published rule does not expose a verifiable topic.')
  const window = rule ? ruleWindow(rule) : null
  if (rule && !window) add('WINDOW_UNVERIFIABLE', 'The published rule does not expose the strategy lookback and forecast horizon needed for compatibility.')
  if (window && (window.lookback_days !== strategy.observation_window.lookback_days || window.horizon_days !== strategy.forecast_horizon_days)) add('WINDOW_MISMATCH', 'The published market window does not match the saved strategy window and horizon.')
  const formula = rule && isRecord(rule.formula) ? rule.formula : null
  if (rule && (!formula || formula.version !== 'growth-threshold-v1' || typeof formula.up_if !== 'string' || typeof formula.down_if !== 'string')) add('RESOLUTION_MISMATCH', 'The published formula does not expose the supported integer growth-threshold UP/DOWN resolution semantics.')
  const observation = rule && isRecord(rule.observation) ? rule.observation : null
  if (observation?.replay === true) add('HISTORICAL_REPLAY', 'The published rule is explicitly marked as a historical replay.')
  return { market_id: market.market_id, market, eligible: reasons.length === 0, reasons, rule_hash: ruleHash, topic, checked_at_utc: checkedAt }
}

function snapshotIdentity(dataset: HistoricalDataset, evaluation: StrategyEvaluation): { id: string; digest: string; cutoff: string } {
  const digest = evaluation.result_digest ?? hashLabel({ dataset: dataset.dataset_id, content_sha256: dataset.content_sha256, end: dataset.observation_end })
  return {
    id: `wikimedia_snapshot_${stableHash(`${dataset.dataset_id}:${dataset.observation_end}:${digest}`)}`,
    digest,
    cutoff: `${dataset.observation_end}T23:59:59Z`,
  }
}

function actionId(policy: AutopilotPolicy, key: string, runTimestamp: string, index: number): string { return `paper_action_${stableHash(JSON.stringify({ policy_id: policy.policy_id, version: policy.version, key, runTimestamp, index }))}` }
function positionId(key: string): string { return `paper_position_${stableHash(key)}` }
function runId(policy: AutopilotPolicy, timestamp: string): string { return `autopilot_run_${stableHash(`${policy.policy_id}:${policy.version}:${timestamp}`)}` }

function makeAction(args: Omit<AutopilotAction, 'action_id'>, index: number): AutopilotAction {
  return { ...args, action_id: actionId({ policy_id: args.policy_id, version: args.policy_version } as AutopilotPolicy, args.idempotency_key, args.run_timestamp_utc, index) }
}

function baseAction(
  policy: AutopilotPolicy,
  idempotencyKey: string,
  timestamp: string,
  snapshot: { id: string | null; digest: string | null; cutoff: string | null },
  market: AutopilotMarket | null,
  decisionCutoff: string | null,
  status: AutopilotActionStatus,
  reasonCode: AutopilotReasonCode,
  explanation: string,
  requestedStake: number,
  stake: number,
  ledger: AutopilotLedgerSnapshot,
  index: number,
  prediction: 'UP' | 'DOWN' | null,
  momentum: number | null,
  sourceDataAsOf: string | null,
  runMode: AutopilotRunMode,
  manualReviewOf: string | null = null,
): AutopilotAction {
  const exposureAfter = status === 'PAPER_ENTRY_APPROVED' ? ledger.current_exposure + stake : ledger.current_exposure
  return makeAction({
    idempotency_key: idempotencyKey,
    policy_id: policy.policy_id,
    policy_version: policy.version,
    strategy_id: policy.strategy_id,
    strategy_hash: policy.strategy_hash,
    evidence_snapshot_id: snapshot.id,
    evidence_digest: snapshot.digest,
    evidence_cutoff_utc: snapshot.cutoff,
    market_id: market?.market_id ?? null,
    market_rule_hash: market?.rule_hash ?? null,
    market_status: market?.status ?? null,
    decision_cutoff_utc: decisionCutoff,
    status,
    reason_code: reasonCode,
    explanation,
    requested_stake: requestedStake,
    stake,
    exposure_before: ledger.current_exposure,
    exposure_after: exposureAfter,
    active_positions_before: ledger.active_positions,
    daily_loss_before: ledger.daily_loss,
    risk_config: { ...policy.risk },
    simulated_position_id: status === 'PAPER_ENTRY_APPROVED' ? positionId(idempotencyKey) : null,
    run_timestamp_utc: iso(timestamp),
    run_mode: runMode,
    strategy_prediction: prediction,
    signal_momentum_bps: momentum,
    source_data_as_of: sourceDataAsOf,
    manual_review_of: manualReviewOf,
    settled_result: null,
    settled_at_utc: null,
  }, index)
}

function previousAction(actions: AutopilotAction[], key: string): AutopilotAction | null {
  return [...actions].reverse().find((action) => action.idempotency_key === key && action.status !== 'ALREADY_PROCESSED') ?? null
}

function makeDuplicate(policy: AutopilotPolicy, previous: AutopilotAction, timestamp: string, ledger: AutopilotLedgerSnapshot, snapshot: { id: string | null; digest: string | null; cutoff: string | null }, market: AutopilotMarket | null, index: number, runMode: AutopilotRunMode): AutopilotAction {
  return baseAction(policy, previous.idempotency_key, timestamp, snapshot, market, previous.decision_cutoff_utc, 'ALREADY_PROCESSED', 'ALREADY_PROCESSED', `This policy, strategy revision, market and decision cutoff were already processed as ${previous.status}; no duplicate paper action was created.`, 0, 0, ledger, index, previous.strategy_prediction, previous.signal_momentum_bps, previous.source_data_as_of, runMode, previous.action_id)
}

function evaluateOne(
  policy: AutopilotPolicy,
  state: AutopilotState,
  market: AutopilotMarket | null,
  assessment: AutopilotMarketAssessment | null,
  evaluation: StrategyEvaluation,
  dataset: HistoricalDataset,
  timestamp: string,
  runMode: AutopilotRunMode,
  index: number,
): AutopilotAction {
  const snapshot = snapshotIdentity(dataset, evaluation)
  const latestDecision = evaluation.decisions.filter((decision) => Date.parse(decision.signal_cutoff_utc) <= Date.parse(timestamp)).at(-1) ?? null
  const decisionCutoff = latestDecision?.signal_cutoff_utc ?? `${evaluation.evaluated_end_utc ?? dataset.observation_end}T23:59:59Z`
  const marketKey = market?.market_id ?? 'no-eligible-market'
  const idempotencyKey = `${policy.policy_id}:${policy.version}:${policy.strategy_hash}:${marketKey}:${decisionCutoff}`
  const ledger = ledgerSnapshot(policy, state.actions, timestamp)
  const prior = previousAction(state.actions, idempotencyKey)
  if (prior) return makeDuplicate(policy, prior, timestamp, ledger, snapshot, market, index, runMode)
  if (policy.status !== 'ACTIVE') return baseAction(policy, `${policy.policy_id}:${policy.version}:paused:${timestamp}`, timestamp, snapshot, market, decisionCutoff, 'PAUSED', policy.status === 'STOPPED' ? 'POLICY_STOPPED' : 'POLICY_PAUSED', policy.status === 'STOPPED' ? 'Policy is stopped. Activate a new policy revision before evaluating.' : 'Policy is paused. Resume it before evaluating new paper actions.', 0, 0, ledger, index, null, null, dataset.observation_end, runMode)
  if (!market && !assessment) return baseAction(policy, idempotencyKey, timestamp, snapshot, null, decisionCutoff, 'MARKET_INELIGIBLE', 'NO_MARKETS_RETURNED', 'No published markets were returned by the market API; no market was fabricated for this policy.', 0, 0, ledger, index, latestDecision?.prediction ?? null, latestDecision?.momentum_bps ?? null, dataset.observation_end, runMode)
  if (assessment && !assessment.eligible) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, decisionCutoff, 'MARKET_INELIGIBLE', assessment.reasons[0]?.code ?? 'RESOLUTION_MISMATCH', assessment.reasons.map((reason) => reason.explanation).join(' '), 0, 0, ledger, index, latestDecision?.prediction ?? null, latestDecision?.momentum_bps ?? null, dataset.observation_end, runMode)
  if (evaluation.status !== 'EVALUATED') return baseAction(policy, idempotencyKey, timestamp, snapshot, market, decisionCutoff, 'INSUFFICIENT_EVIDENCE', 'MISSING_EVIDENCE', evaluation.reason ?? 'The selected strategy could not be evaluated on supported genuine observations.', 0, 0, ledger, index, null, null, dataset.observation_end, runMode)
  if (runMode === 'FORWARD_EVALUATION' && dataset.observation_end < day(timestamp)) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, decisionCutoff, 'INSUFFICIENT_EVIDENCE', 'STALE_EVIDENCE', `The latest supported observation is ${dataset.observation_end}; it is stale for this forward evaluation cutoff.`, 0, 0, ledger, index, latestDecision?.prediction ?? null, latestDecision?.momentum_bps ?? null, dataset.observation_end, runMode)
  if (!latestDecision) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, decisionCutoff, 'INSUFFICIENT_EVIDENCE', evaluation.unavailable_windows ? 'MISSING_EVIDENCE' : 'NO_SIGNAL', evaluation.unavailable_windows ? 'No complete evidence window was available for an executable signal.' : 'The strategy did not produce a signal on the latest complete eligible window.', 0, 0, ledger, index, null, null, dataset.observation_end, runMode)

  const requestedStake = stakeFor(policy.risk)
  if (ledger.daily_loss >= policy.risk.daily_loss_limit_credits) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, latestDecision.signal_cutoff_utc, 'BLOCKED_BY_RISK', 'DAILY_LOSS_LIMIT', `Daily virtual losses reached ${ledger.daily_loss} credits, the configured limit.`, requestedStake, 0, ledger, index, latestDecision.prediction, latestDecision.momentum_bps, dataset.observation_end, runMode)
  if (ledger.active_positions >= policy.risk.max_positions) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, latestDecision.signal_cutoff_utc, 'BLOCKED_BY_RISK', 'MAX_POSITIONS', `The policy already has ${ledger.active_positions} active paper position${ledger.active_positions === 1 ? '' : 's'}, the configured maximum.`, requestedStake, 0, ledger, index, latestDecision.prediction, latestDecision.momentum_bps, dataset.observation_end, runMode)
  if (policy.risk.cooldown_seconds > 0 && ledger.last_action_at_utc && Date.parse(timestamp) - Date.parse(ledger.last_action_at_utc) < policy.risk.cooldown_seconds * 1000) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, latestDecision.signal_cutoff_utc, 'COOLDOWN', 'COOLDOWN', `The decision cooldown of ${policy.risk.cooldown_seconds} seconds has not elapsed since the last policy action.`, requestedStake, 0, ledger, index, latestDecision.prediction, latestDecision.momentum_bps, dataset.observation_end, runMode)
  if (requestedStake > ledger.available_budget) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, latestDecision.signal_cutoff_utc, 'BLOCKED_BY_RISK', 'BUDGET_EXHAUSTED', `Requested stake ${requestedStake} exceeds available virtual budget ${ledger.available_budget}.`, requestedStake, 0, ledger, index, latestDecision.prediction, latestDecision.momentum_bps, dataset.observation_end, runMode)
  if (ledger.current_exposure + requestedStake > policy.risk.max_exposure_credits) return baseAction(policy, idempotencyKey, timestamp, snapshot, market, latestDecision.signal_cutoff_utc, 'BLOCKED_BY_RISK', 'MAX_EXPOSURE', `Requested exposure would reach ${ledger.current_exposure + requestedStake}, above the configured maximum ${policy.risk.max_exposure_credits}.`, requestedStake, 0, ledger, index, latestDecision.prediction, latestDecision.momentum_bps, dataset.observation_end, runMode)
  if (policy.mode === 'MANUAL_REVIEW') return baseAction(policy, idempotencyKey, timestamp, snapshot, market, latestDecision.signal_cutoff_utc, 'NEEDS_MANUAL_REVIEW', 'MANUAL_REVIEW_REQUIRED', 'Risk checks passed, but this policy requires a human review before creating a paper position.', requestedStake, requestedStake, ledger, index, latestDecision.prediction, latestDecision.momentum_bps, dataset.observation_end, runMode)
  return baseAction(policy, idempotencyKey, timestamp, snapshot, market, latestDecision.signal_cutoff_utc, 'PAPER_ENTRY_APPROVED', 'PAPER_POLICY_ALLOWED', 'Risk checks passed in paper-auto mode; a virtual position was recorded without wallet or market execution.', requestedStake, requestedStake, ledger, index, latestDecision.prediction, latestDecision.momentum_bps, dataset.observation_end, runMode)
}

export function evaluateAutopilot(
  state: AutopilotState,
  strategy: StrategyDefinition,
  dataset: HistoricalDataset,
  markets: AutopilotMarket[],
  options: { now: string; run_mode?: AutopilotRunMode; market_error?: string | null } = { now: new Date().toISOString() },
): AutopilotEvaluationResult {
  if (!state.policy) throw new Error('Activate a policy before evaluating it.')
  const policy = state.policy
  const timestamp = iso(options.now)
  const runMode = options.run_mode ?? 'FORWARD_EVALUATION'
  const evaluation = evaluateStrategy(strategy, dataset)
  const assessments = markets.map((market) => assessMarketCompatibility(strategy, market, timestamp))
  const selected = assessments.filter((assessment) => assessment.eligible)
  let nextActions: AutopilotAction[] = []
  let workingState = state
  if (options.market_error) {
    const snapshot = snapshotIdentity(dataset, evaluation)
    const ledger = ledgerSnapshot(policy, state.actions, timestamp)
    const key = `${policy.policy_id}:${policy.version}:market-api:${day(timestamp)}`
    const prior = previousAction(state.actions, key)
    const action = prior ? makeDuplicate(policy, prior, timestamp, ledger, snapshot, null, 0, runMode) : baseAction(policy, key, timestamp, snapshot, null, null, 'INSUFFICIENT_EVIDENCE', 'MARKET_DATA_UNAVAILABLE', options.market_error, 0, 0, ledger, 0, null, null, dataset.observation_end, runMode)
    nextActions = [action]
    workingState = { ...state, actions: [...state.actions, action] }
  } else if (!markets.length) {
    const action = evaluateOne(policy, state, null, null, evaluation, dataset, timestamp, runMode, 0)
    nextActions = [action]
    workingState = { ...state, actions: [...state.actions, action] }
  } else {
    assessments.forEach((assessment, index) => {
      const action = evaluateOne(policy, workingState, assessment.market, assessment, evaluation, dataset, timestamp, runMode, index)
      nextActions.push(action)
      workingState = { ...workingState, actions: [...workingState.actions, action] }
    })
  }
  const nextState = workingState
  const ledger = ledgerSnapshot(policy, nextState.actions, timestamp)
  return {
    state: nextState,
    run_id: runId(policy, timestamp),
    run_timestamp_utc: timestamp,
    run_mode: runMode,
    strategy_evaluation: evaluation,
    market_assessments: assessments,
    actions: nextActions,
    eligible_market_count: selected.length,
    ledger,
    no_eligible_market_reason: selected.length ? null : options.market_error ?? (markets.length ? 'No published market passed the source, topic, rule, deadline and resolution checks.' : 'No published markets were returned by the market API.'),
  }
}

export function approveManualReview(state: AutopilotState, actionId: string, now: string): { state: AutopilotState; action: AutopilotAction | null } {
  if (!state.policy) return { state, action: null }
  const pending = state.actions.find((action) => action.action_id === actionId && action.status === 'NEEDS_MANUAL_REVIEW')
  if (!pending || pending.policy_id !== state.policy.policy_id || pending.policy_version !== state.policy.version || state.actions.some((action) => action.idempotency_key === pending.idempotency_key && action.status === 'PAPER_ENTRY_APPROVED')) return { state, action: null }
  const timestamp = iso(now)
  const ledger = ledgerSnapshot(state.policy, state.actions, timestamp)
  const requested = pending.requested_stake
  let status: AutopilotActionStatus = 'PAPER_ENTRY_APPROVED'
  let reason: AutopilotReasonCode = 'MANUAL_REVIEW_REQUIRED'
  let explanation = 'Manual review approved the paper entry after rechecking the current local risk ledger; no wallet or market execution occurred.'
  if (state.policy.status !== 'ACTIVE') { status = 'PAUSED'; reason = state.policy.status === 'STOPPED' ? 'POLICY_STOPPED' : 'POLICY_PAUSED'; explanation = 'The policy is not active, so the reviewed paper entry was not created.' }
  else if (ledger.daily_loss >= state.policy.risk.daily_loss_limit_credits) { status = 'BLOCKED_BY_RISK'; reason = 'DAILY_LOSS_LIMIT'; explanation = 'The daily virtual-loss limit was reached before manual approval.' }
  else if (ledger.active_positions >= state.policy.risk.max_positions) { status = 'BLOCKED_BY_RISK'; reason = 'MAX_POSITIONS'; explanation = 'The simultaneous-position limit was reached before manual approval.' }
  else if (ledger.current_exposure + requested > state.policy.risk.max_exposure_credits) { status = 'BLOCKED_BY_RISK'; reason = 'MAX_EXPOSURE'; explanation = 'The maximum exposure was reached before manual approval.' }
  const action = baseAction(state.policy, pending.idempotency_key, timestamp, { id: pending.evidence_snapshot_id, digest: pending.evidence_digest, cutoff: pending.evidence_cutoff_utc }, pending.market_id ? ({ market_id: pending.market_id, rule_hash: pending.market_rule_hash, status: pending.market_status } as Market) : null, pending.decision_cutoff_utc, status, reason, explanation, requested, status === 'PAPER_ENTRY_APPROVED' ? requested : 0, ledger, 0, pending.strategy_prediction, pending.signal_momentum_bps, pending.source_data_as_of, 'FORWARD_EVALUATION', pending.action_id)
  return { state: { ...state, actions: [...state.actions, action] }, action }
}

export function actionStatusLabel(status: AutopilotActionStatus): string {
  return status === 'PAPER_ENTRY_APPROVED' ? 'Paper entry approved' : status === 'NEEDS_MANUAL_REVIEW' ? 'Needs manual review' : status === 'ALREADY_PROCESSED' ? 'Already processed' : status === 'MARKET_INELIGIBLE' ? 'Market ineligible' : status === 'INSUFFICIENT_EVIDENCE' ? 'Insufficient evidence' : status === 'BLOCKED_BY_RISK' ? 'Blocked by risk' : status === 'COOLDOWN' ? 'Cooldown' : 'Paused'
}
