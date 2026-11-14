import {
  canonicalStrategyHash,
  createStrategyFromDraft,
  evaluateStrategy,
  type StrategyDefinition,
  type StrategyEvaluation,
  type StrategyEvaluationDecision,
  type StrategyEvaluationUnavailable,
} from '../strategy/strategy.ts'
import type { HistoricalDataset } from '../practice/backtest.ts'

export const ARENA_METHODOLOGY_VERSION = 'notch-agent-arena/1'
export const ARENA_PARTICIPANT_VERSION = 'notch-agent-arena-participant/1'
export const ARENA_RISK_VERSION = 'notch-agent-arena-risk/1'
export const ARENA_LOOKBACK_DAYS = 7
export const ARENA_HORIZON_DAYS = 7
export const ARENA_DEFAULT_THRESHOLD_PERCENT = 5
export const ARENA_DEFAULT_INITIAL_CREDITS = 1_000
export const ARENA_DEFAULT_RISK_POLICY: ArenaRiskPolicy = {
  version: ARENA_RISK_VERSION,
  initial_credits: ARENA_DEFAULT_INITIAL_CREDITS,
  stake_fraction: 0.1,
  max_position_fraction: 0.25,
  minimum_stake: 1,
  settlement: 'correct_plus_equal_virtual_reward',
}

export type ArenaParticipantKind = 'DETERMINISTIC_BOT' | 'BASELINE' | 'USER_STRATEGY'
export type ArenaBehavior = 'ATTENTION_MOMENTUM' | 'CONTRARIAN_REVERSAL' | 'ALWAYS_UP' | 'ALWAYS_DOWN' | 'SAVED_STRATEGY'
export type ArenaDecisionStatus = 'SETTLED' | 'SKIPPED' | 'UNAVAILABLE' | 'VOID'
export type ArenaParticipantStatus = 'EVALUATED' | 'UNSUPPORTED' | 'INSUFFICIENT_DATA'

export interface ArenaRiskPolicy {
  version: typeof ARENA_RISK_VERSION
  initial_credits: number
  stake_fraction: number
  max_position_fraction: number
  minimum_stake: number
  settlement: 'correct_plus_equal_virtual_reward'
}

export interface ArenaParticipant {
  participant_id: string
  version: typeof ARENA_PARTICIPANT_VERSION
  name: string
  kind: ArenaParticipantKind
  behavior: ArenaBehavior
  description: string
  strategy: StrategyDefinition | null
  strategy_schema_version: string | null
  strategy_hash: string
  participant_config_hash: string
  deterministic: true
  ai_agent: false
}

export interface ArenaExcludedParticipant {
  participant_id: string
  name: string
  reason: string
  strategy_hash: string | null
}

export interface ArenaParticipantSet {
  participants: ArenaParticipant[]
  excluded: ArenaExcludedParticipant[]
}

export interface ArenaDecisionRecord {
  decision_id: string
  participant_id: string
  signal_date: string
  signal_cutoff_utc: string
  status: ArenaDecisionStatus
  reason: string | null
  prediction: 'UP' | 'DOWN' | null
  outcome: 'UP' | 'DOWN' | 'VOID' | null
  correct: boolean | null
  momentum_bps: number | null
  threshold_bps: number | null
  stake: number
  bankroll_before: number
  bankroll_after: number
  risk_limit_applied: boolean
  evidence_refs: string[]
  signal_evidence_refs: string[]
  outcome_evidence_refs: string[]
}

export interface ArenaParticipantResult {
  participant_id: string
  participant_name: string
  participant_kind: ArenaParticipantKind
  strategy_hash: string
  status: ArenaParticipantStatus
  reason: string | null
  starting_credits: number
  ending_credits: number
  correct: number
  incorrect: number
  pending: number
  voided: number
  skipped: number
  unavailable: number
  insufficient_balance_skips: number
  signals_generated: number
  accuracy: number | null
  sample_size: number
  max_drawdown_credits: number | null
  max_drawdown_percent: number | null
  risk_limit_violations_prevented: number
  eligible_windows: number
  candidate_windows: number
  decision_records: ArenaDecisionRecord[]
  evaluation: StrategyEvaluation
}

export interface ArenaLeaderboardRow extends ArenaParticipantResult {
  rank: number
  ranking_basis: 'ENDING_CREDITS_THEN_ACCURACY_THEN_CORRECT_THEN_STABLE_ID'
}

export interface ArenaDatasetIdentity {
  dataset_id: string
  version: number
  label: string
  content_sha256: string
  source_fixture_sha256: string
  source_url: string
  observation_start_utc: string
  observation_end_utc: string
}

export interface ArenaMatch {
  schema_version: typeof ARENA_METHODOLOGY_VERSION
  match_id: string
  methodology_version: typeof ARENA_METHODOLOGY_VERSION
  participant_version: typeof ARENA_PARTICIPANT_VERSION
  dataset: ArenaDatasetIdentity
  start_date_utc: string
  end_date_utc: string
  evidence_cutoff_utc: string
  initial_virtual_bankroll: number
  risk_policy: ArenaRiskPolicy
  scoring: {
    correct: 'stake_plus_equal_virtual_reward'
    incorrect: 'stake_lost'
    void: 'stake_refunded'
    pending: 'not_settled'
  }
  participant_configs: ArenaParticipant[]
  excluded_participants: ArenaExcludedParticipant[]
  shared_candidate_dates: string[]
  shared_eligible_dates: string[]
  shared_benchmark_signal_dates: string[]
  overlapping_windows: {
    window_step_days: 1
    full_span_days: number
    overlap_days: number
    disclosure: string
  }
  results: ArenaParticipantResult[]
  leaderboard: ArenaLeaderboardRow[]
  decision_records: ArenaDecisionRecord[]
  result_digest: string
  execution: {
    wallet_action: false
    signing: false
    transaction: false
    market_entry: false
    ai_inference: false
  }
}

function stableHash(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function hashLabel(value: unknown): string { return `fnv1a32:${stableHash(JSON.stringify(value))}` }

function strategyFromDraft(name: string, predictedOutcome: 'UP' | 'DOWN', direction: 'RISING' | 'FALLING' = 'RISING'): StrategyDefinition {
  const result = createStrategyFromDraft({
    name,
    source_id: 'wikimedia-pageviews-v1',
    topic: 'Nvidia',
    lookback_days: ARENA_LOOKBACK_DAYS,
    signal_direction: direction,
    threshold_percent: ARENA_DEFAULT_THRESHOLD_PERCENT,
    forecast_horizon_days: ARENA_HORIZON_DAYS,
    predicted_outcome: predictedOutcome,
    missing_data_policy: 'NO_SIGNAL',
  })
  if (!result.ok) throw new Error(result.errors.join(' '))
  return result.value
}

function participantHash(input: Pick<ArenaParticipant, 'participant_id' | 'version' | 'behavior' | 'strategy_hash'>): string {
  return hashLabel(input)
}

function makeParticipant(
  participant_id: string,
  name: string,
  kind: ArenaParticipantKind,
  behavior: ArenaBehavior,
  description: string,
  strategy: StrategyDefinition | null,
): ArenaParticipant {
  const strategyHash = strategy ? canonicalStrategyHash(strategy) : hashLabel({ participant_id, version: ARENA_PARTICIPANT_VERSION, behavior })
  const base: Pick<ArenaParticipant, 'participant_id' | 'version' | 'behavior' | 'strategy_hash'> = { participant_id, version: ARENA_PARTICIPANT_VERSION, behavior, strategy_hash: strategyHash }
  return {
    ...base,
    name,
    kind,
    description,
    strategy,
    strategy_schema_version: strategy?.schema_version ?? null,
    strategy_hash: strategyHash,
    participant_config_hash: participantHash(base),
    deterministic: true,
    ai_agent: false,
  }
}

export function builtInArenaParticipants(): ArenaParticipant[] {
  return [
    makeParticipant(
      'bot_attention_momentum_v1',
      'Attention Momentum',
      'DETERMINISTIC_BOT',
      'ATTENTION_MOMENTUM',
      'Falling seven-day attention momentum predicts DOWN after a 5% threshold.',
      strategyFromDraft('Attention Momentum', 'DOWN', 'FALLING'),
    ),
    makeParticipant(
      'bot_contrarian_reversal_v1',
      'Contrarian / Reversal',
      'DETERMINISTIC_BOT',
      'CONTRARIAN_REVERSAL',
      'Uses the same falling attention trigger as Momentum, then takes the opposite UP call.',
      strategyFromDraft('Contrarian / Reversal', 'UP', 'FALLING'),
    ),
    makeParticipant(
      'baseline_always_up_v1',
      'Always-UP baseline',
      'BASELINE',
      'ALWAYS_UP',
      'Calls UP on every shared benchmark signal date. Benchmark only; not a strategy claim.',
      null,
    ),
    makeParticipant(
      'baseline_always_down_v1',
      'Always-DOWN baseline',
      'BASELINE',
      'ALWAYS_DOWN',
      'Calls DOWN on every shared benchmark signal date. Benchmark only; not a strategy claim.',
      null,
    ),
  ]
}

export function isArenaCompatible(strategy: StrategyDefinition): { ok: true } | { ok: false; reason: string } {
  if (strategy.source.topic !== 'Nvidia') return { ok: false, reason: 'Arena V1 uses the frozen Nvidia Wikimedia dataset only.' }
  if (strategy.observation_window.lookback_days !== ARENA_LOOKBACK_DAYS || strategy.forecast_horizon_days !== ARENA_HORIZON_DAYS) {
    return { ok: false, reason: `Arena V1 requires ${ARENA_LOOKBACK_DAYS}-day signal windows and a ${ARENA_HORIZON_DAYS}-day target horizon so every participant receives the same cutoffs.` }
  }
  if (strategy.source.id !== 'wikimedia-pageviews-v1' || strategy.source.methodology_version !== 'wikimedia-pageviews-v1') {
    return { ok: false, reason: 'The saved strategy does not use the supported Wikimedia Pageviews methodology.' }
  }
  return { ok: true }
}

export function arenaParticipants(userStrategy: StrategyDefinition | null = null): ArenaParticipantSet {
  const participants = builtInArenaParticipants()
  const excluded: ArenaExcludedParticipant[] = []
  if (!userStrategy) return { participants, excluded }
  const compatibility = isArenaCompatible(userStrategy)
  if (!compatibility.ok) {
    excluded.push({ participant_id: `saved_${userStrategy.strategy_id}`, name: `Saved: ${userStrategy.name}`, reason: compatibility.reason, strategy_hash: canonicalStrategyHash(userStrategy) })
    return { participants, excluded }
  }
  participants.push(makeParticipant(
    `saved_${userStrategy.strategy_id}`,
    `Saved: ${userStrategy.name}`,
    'USER_STRATEGY',
    'SAVED_STRATEGY',
    'One validated strategy loaded from this device; no profile or AI identity is implied.',
    userStrategy,
  ))
  return { participants, excluded }
}

function parseDay(value: string): number {
  const timestamp = Date.parse(`${value}T00:00:00Z`)
  if (!Number.isFinite(timestamp)) throw new Error(`Invalid historical date: ${value}`)
  return timestamp
}

function dayString(timestamp: number): string { return new Date(timestamp).toISOString().slice(0, 10) }
function shift(value: string, offset: number): string { return dayString(parseDay(value) + offset * 86_400_000) }
function dateRange(start: string, end: string): string[] {
  const rows: string[] = []
  for (let cursor = parseDay(start), finish = parseDay(end); cursor <= finish; cursor += 86_400_000) rows.push(dayString(cursor))
  return rows
}

function candidateDates(dataset: HistoricalDataset): string[] {
  if (!dataset.observations.length) return []
  const dates = dataset.observations.map((item) => item.date).filter((date) => Number.isFinite(Date.parse(`${date}T00:00:00Z`))).sort()
  const first = shift(dates[0], ARENA_LOOKBACK_DAYS * 2 - 1)
  const last = shift(dates.at(-1)!, -ARENA_HORIZON_DAYS)
  return first <= last ? dateRange(first, last) : []
}

function requiredDates(signalDate: string): string[] {
  const previous = dateRange(shift(signalDate, -(ARENA_LOOKBACK_DAYS * 2 - 1)), shift(signalDate, -ARENA_LOOKBACK_DAYS))
  const signal = dateRange(shift(signalDate, -(ARENA_LOOKBACK_DAYS - 1)), signalDate)
  const target = dateRange(shift(signalDate, 1), shift(signalDate, ARENA_HORIZON_DAYS))
  return [...previous, ...signal, ...target]
}

function evidenceRef(dataset: HistoricalDataset, date: string): string {
  return `wikimedia:${dataset.source.project}:${dataset.source.article}:${date}`
}

function evidenceRefsFor(dataset: HistoricalDataset, signalDate: string): { all: string[]; signal: string[]; outcome: string[] } {
  const values = new Set(dataset.observations.map((item) => item.date))
  const dates = requiredDates(signalDate)
  const signalDates = dates.slice(0, ARENA_LOOKBACK_DAYS * 2)
  const outcomeDates = dates.slice(ARENA_LOOKBACK_DAYS * 2)
  const refs = (items: string[]) => items.filter((date) => values.has(date)).map((date) => evidenceRef(dataset, date))
  const signal = refs(signalDates)
  const outcome = refs(outcomeDates)
  return { all: [...signal, ...outcome], signal, outcome }
}

function unavailableByDate(items: StrategyEvaluationUnavailable[]): Map<string, StrategyEvaluationUnavailable> {
  return new Map(items.map((item) => [item.signal_date, item]))
}

function decisionByDate(items: StrategyEvaluationDecision[]): Map<string, StrategyEvaluationDecision> {
  return new Map(items.map((item) => [item.signal_date, item]))
}

function evaluationForParticipant(participant: ArenaParticipant, dataset: HistoricalDataset, reference: StrategyEvaluation): StrategyEvaluation {
  if (participant.behavior === 'ALWAYS_UP' || participant.behavior === 'ALWAYS_DOWN') return reference
  return participant.strategy ? evaluateStrategy(participant.strategy, dataset) : reference
}

function policyValid(policy: ArenaRiskPolicy): boolean {
  return Number.isSafeInteger(policy.initial_credits) && policy.initial_credits >= 0
    && Number.isFinite(policy.stake_fraction) && policy.stake_fraction >= 0 && policy.stake_fraction <= 1
    && Number.isFinite(policy.max_position_fraction) && policy.max_position_fraction >= 0 && policy.max_position_fraction <= 1
    && Number.isSafeInteger(policy.minimum_stake) && policy.minimum_stake >= 0
}

function emptyResult(participant: ArenaParticipant, evaluation: StrategyEvaluation, policy: ArenaRiskPolicy, reason: string | null): ArenaParticipantResult {
  return {
    participant_id: participant.participant_id,
    participant_name: participant.name,
    participant_kind: participant.kind,
    strategy_hash: participant.strategy_hash,
    status: evaluation.status,
    reason,
    starting_credits: policy.initial_credits,
    ending_credits: policy.initial_credits,
    correct: 0,
    incorrect: 0,
    pending: 0,
    voided: 0,
    skipped: 0,
    unavailable: 0,
    insufficient_balance_skips: 0,
    signals_generated: 0,
    accuracy: null,
    sample_size: 0,
    max_drawdown_credits: null,
    max_drawdown_percent: null,
    risk_limit_violations_prevented: 0,
    eligible_windows: evaluation.eligible_windows,
    candidate_windows: evaluation.candidate_windows,
    decision_records: [],
    evaluation,
  }
}

function simulateParticipant(
  participant: ArenaParticipant,
  evaluation: StrategyEvaluation,
  reference: StrategyEvaluation,
  dataset: HistoricalDataset,
  policy: ArenaRiskPolicy,
): ArenaParticipantResult {
  if (evaluation.status !== 'EVALUATED') return emptyResult(participant, evaluation, policy, evaluation.reason)
  const candidates = candidateDates(dataset)
  const unavailable = unavailableByDate(evaluation.unavailable)
  const decisions = decisionByDate(evaluation.decisions)
  const eligible = new Set(reference.eligible_window_dates)
  let bankroll = policy.initial_credits
  let peak = bankroll
  let maxDrawdown = 0
  let correct = 0
  let incorrect = 0
  let pending = 0
  let voided = 0
  let skipped = 0
  let unavailableCount = 0
  let insufficientBalanceSkips = 0
  let signals = 0
  let riskPrevented = 0
  const records: ArenaDecisionRecord[] = []

  for (const signalDate of candidates) {
    const refs = evidenceRefsFor(dataset, signalDate)
    const missing = unavailable.get(signalDate)
    const candidateDecision = decisions.get(signalDate)
    const commonEligible = eligible.has(signalDate)
    if (missing) {
      unavailableCount += 1
      records.push({
        decision_id: `${participant.participant_id}:${signalDate}`,
        participant_id: participant.participant_id,
        signal_date: signalDate,
        signal_cutoff_utc: `${signalDate}T23:59:59Z`,
        status: 'UNAVAILABLE',
        reason: missing.reason === 'ZERO_BASELINE' ? 'ZERO_BASELINE' : 'MISSING_OBSERVATIONS',
        prediction: null,
        outcome: null,
        correct: null,
        momentum_bps: null,
        threshold_bps: participant.strategy?.threshold_bps ?? null,
        stake: 0,
        bankroll_before: bankroll,
        bankroll_after: bankroll,
        risk_limit_applied: false,
        evidence_refs: refs.all,
        signal_evidence_refs: refs.signal,
        outcome_evidence_refs: refs.outcome,
      })
      continue
    }
    const prediction = participant.behavior === 'ALWAYS_UP' ? 'UP' : participant.behavior === 'ALWAYS_DOWN' ? 'DOWN' : candidateDecision?.prediction ?? null
    if (!commonEligible || !candidateDecision && !prediction) {
      skipped += 1
      records.push({
        decision_id: `${participant.participant_id}:${signalDate}`,
        participant_id: participant.participant_id,
        signal_date: signalDate,
        signal_cutoff_utc: `${signalDate}T23:59:59Z`,
        status: 'SKIPPED',
        reason: 'SIGNAL_DID_NOT_CLEAR_THRESHOLD',
        prediction: null,
        outcome: null,
        correct: null,
        momentum_bps: candidateDecision?.momentum_bps ?? null,
        threshold_bps: participant.strategy?.threshold_bps ?? null,
        stake: 0,
        bankroll_before: bankroll,
        bankroll_after: bankroll,
        risk_limit_applied: false,
        evidence_refs: refs.all,
        signal_evidence_refs: refs.signal,
        outcome_evidence_refs: refs.outcome,
      })
      continue
    }
    const sourceDecision = candidateDecision ?? reference.decisions.find((item) => item.signal_date === signalDate) ?? null
    if (!sourceDecision || !prediction) {
      skipped += 1
      continue
    }
    signals += 1
    const bankrollBefore = bankroll
    const requested = Math.floor(bankroll * policy.stake_fraction)
    const cap = Math.floor(policy.initial_credits * policy.max_position_fraction)
    const capped = Math.min(requested, cap, bankroll)
    const riskApplied = requested > capped
    if (riskApplied) riskPrevented += 1
    if (capped < policy.minimum_stake || capped <= 0) {
      insufficientBalanceSkips += 1
      skipped += 1
      records.push({
        decision_id: `${participant.participant_id}:${signalDate}`,
        participant_id: participant.participant_id,
        signal_date: signalDate,
        signal_cutoff_utc: sourceDecision.signal_cutoff_utc,
        status: 'SKIPPED',
        reason: 'INSUFFICIENT_BALANCE',
        prediction,
        outcome: sourceDecision.outcome,
        correct: null,
        momentum_bps: sourceDecision.momentum_bps,
        threshold_bps: sourceDecision.threshold_bps,
        stake: 0,
        bankroll_before: bankrollBefore,
        bankroll_after: bankroll,
        risk_limit_applied: riskApplied,
        evidence_refs: refs.all,
        signal_evidence_refs: refs.signal,
        outcome_evidence_refs: refs.outcome,
      })
      continue
    }
    const outcome = sourceDecision.outcome
    const isCorrect = prediction === outcome
    if (isCorrect) { correct += 1; bankroll += capped } else { incorrect += 1; bankroll -= capped }
    peak = Math.max(peak, bankroll)
    maxDrawdown = Math.max(maxDrawdown, peak - bankroll)
    records.push({
      decision_id: `${participant.participant_id}:${signalDate}`,
      participant_id: participant.participant_id,
      signal_date: signalDate,
      signal_cutoff_utc: sourceDecision.signal_cutoff_utc,
      status: 'SETTLED',
      reason: null,
      prediction,
      outcome,
      correct: isCorrect,
      momentum_bps: sourceDecision.momentum_bps,
      threshold_bps: sourceDecision.threshold_bps,
      stake: capped,
      bankroll_before: bankrollBefore,
      bankroll_after: bankroll,
      risk_limit_applied: riskApplied,
      evidence_refs: refs.all,
      signal_evidence_refs: refs.signal,
      outcome_evidence_refs: refs.outcome,
    })
  }
  const settled = correct + incorrect
  return {
    participant_id: participant.participant_id,
    participant_name: participant.name,
    participant_kind: participant.kind,
    strategy_hash: participant.strategy_hash,
    status: 'EVALUATED',
    reason: null,
    starting_credits: policy.initial_credits,
    ending_credits: bankroll,
    correct,
    incorrect,
    pending,
    voided,
    skipped,
    unavailable: unavailableCount,
    insufficient_balance_skips: insufficientBalanceSkips,
    signals_generated: signals,
    accuracy: settled ? correct / settled * 100 : null,
    sample_size: settled,
    max_drawdown_credits: settled ? maxDrawdown : null,
    max_drawdown_percent: settled && policy.initial_credits > 0 ? maxDrawdown / policy.initial_credits * 100 : null,
    risk_limit_violations_prevented: riskPrevented,
    eligible_windows: reference.eligible_windows,
    candidate_windows: reference.candidate_windows,
    decision_records: records,
    evaluation,
  }
}

function rankResults(results: ArenaParticipantResult[]): ArenaLeaderboardRow[] {
  return [...results]
    .sort((a, b) => b.ending_credits - a.ending_credits || (b.accuracy ?? -1) - (a.accuracy ?? -1) || b.correct - a.correct || a.participant_id.localeCompare(b.participant_id))
    .map((result, index) => ({ ...result, rank: index + 1, ranking_basis: 'ENDING_CREDITS_THEN_ACCURACY_THEN_CORRECT_THEN_STABLE_ID' }))
}

function datasetIdentity(dataset: HistoricalDataset): ArenaDatasetIdentity {
  return {
    dataset_id: dataset.dataset_id,
    version: dataset.version,
    label: dataset.label,
    content_sha256: dataset.content_sha256,
    source_fixture_sha256: dataset.retrieval_provenance.source_fixture_sha256,
    source_url: dataset.source.url,
    observation_start_utc: dataset.observation_start,
    observation_end_utc: dataset.observation_end,
  }
}

export function runArenaMatch(
  dataset: HistoricalDataset,
  participants: ArenaParticipant[],
  options: { risk_policy?: Partial<ArenaRiskPolicy>; excluded_participants?: ArenaExcludedParticipant[] } = {},
): ArenaMatch {
  const policy: ArenaRiskPolicy = { ...ARENA_DEFAULT_RISK_POLICY, ...(options.risk_policy ?? {}) }
  if (!policyValid(policy)) throw new Error('Arena risk policy must use non-negative numeric limits and integer credits.')
  const referenceStrategy = builtInArenaParticipants()[0].strategy!
  const reference = evaluateStrategy(referenceStrategy, dataset)
  const candidateDatesList = candidateDates(dataset)
  const results = participants.map((participant) => {
    const evaluation = evaluationForParticipant(participant, dataset, reference)
    return simulateParticipant(participant, evaluation, reference, dataset, policy)
  })
  const leaderboard = rankResults(results)
  const publicPayload = {
    methodology_version: ARENA_METHODOLOGY_VERSION,
    participant_version: ARENA_PARTICIPANT_VERSION,
    dataset: datasetIdentity(dataset),
    start_date_utc: dataset.observation_start,
    end_date_utc: dataset.observation_end,
    evidence_cutoff_utc: `${dataset.observation_end}T23:59:59Z`,
    initial_virtual_bankroll: policy.initial_credits,
    risk_policy: policy,
    participants,
    excluded_participants: options.excluded_participants ?? [],
    shared_candidate_dates: candidateDatesList,
    shared_eligible_dates: reference.eligible_window_dates,
    shared_benchmark_signal_dates: reference.decisions.map((decision) => decision.signal_date),
    results,
    leaderboard,
  }
  const matchId = `arena_match_${stableHash(JSON.stringify(publicPayload))}`
  const fullSpan = ARENA_LOOKBACK_DAYS * 2 + ARENA_HORIZON_DAYS
  const decisionRecords = results.flatMap((result) => result.decision_records).sort((a, b) => a.signal_date.localeCompare(b.signal_date) || a.participant_id.localeCompare(b.participant_id))
  const resultDigest = hashLabel({ ...publicPayload, result_digest: null })
  return {
    schema_version: ARENA_METHODOLOGY_VERSION,
    match_id: matchId,
    methodology_version: ARENA_METHODOLOGY_VERSION,
    participant_version: ARENA_PARTICIPANT_VERSION,
    dataset: datasetIdentity(dataset),
    start_date_utc: dataset.observation_start,
    end_date_utc: dataset.observation_end,
    evidence_cutoff_utc: `${dataset.observation_end}T23:59:59Z`,
    initial_virtual_bankroll: policy.initial_credits,
    risk_policy: policy,
    scoring: {
      correct: 'stake_plus_equal_virtual_reward',
      incorrect: 'stake_lost',
      void: 'stake_refunded',
      pending: 'not_settled',
    },
    participant_configs: participants,
    excluded_participants: options.excluded_participants ?? [],
    shared_candidate_dates: candidateDatesList,
    shared_eligible_dates: reference.eligible_window_dates,
    shared_benchmark_signal_dates: reference.decisions.map((decision) => decision.signal_date),
    overlapping_windows: {
      window_step_days: 1,
      full_span_days: fullSpan,
      overlap_days: fullSpan - 1,
      disclosure: `Candidate windows advance one UTC day and overlap by ${fullSpan - 1} of ${fullSpan} observation days; virtual results are not independent trials.`,
    },
    results,
    leaderboard,
    decision_records: decisionRecords,
    result_digest: resultDigest,
    execution: {
      wallet_action: false,
      signing: false,
      transaction: false,
      market_entry: false,
      ai_inference: false,
    },
  }
}

export function arenaMatchSummary(match: ArenaMatch): string {
  return `${match.match_id} · ${match.dataset.dataset_id} · ${match.result_digest}`
}
