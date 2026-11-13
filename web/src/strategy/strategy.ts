import { growthBpsFromSums, shiftDay, type HistoricalDataset } from '../practice/backtest.ts'

export const STRATEGY_SCHEMA_VERSION = 'notch.strategy/1'
export const STRATEGY_STORAGE_VERSION = 1
export const STRATEGY_STORAGE_KEY = 'notch.strategy.builder.v1'
export const STRATEGY_SOURCE_ID = 'wikimedia-pageviews-v1'
export const STRATEGY_SOURCE_METHODOLOGY_VERSION = 'wikimedia-pageviews-v1'
export const STRATEGY_EVALUATION_METHODOLOGY_VERSION = 'notch-historical-evaluation/1'
export const SUPPORTED_WINDOW_DAYS = [1, 3, 7, 14, 30] as const
export const STRATEGY_MISSING_POLICIES = ['NO_SIGNAL', 'UNAVAILABLE'] as const

export const SUPPORTED_TOPICS = [
  { value: 'Nvidia', aliases: ['nvidia', 'nvidia corporation', 'nvda'] },
  { value: 'Bitcoin', aliases: ['bitcoin', 'btc'] },
  { value: 'ChatGPT', aliases: ['chatgpt', 'chat gpt'] },
  { value: 'Artificial intelligence', aliases: ['artificial intelligence', 'ai'] },
] as const

export type SupportedTopic = typeof SUPPORTED_TOPICS[number]['value']
export type SignalDirection = 'RISING' | 'FALLING'
export type PredictedOutcome = 'UP' | 'DOWN'
export type MissingDataPolicy = typeof STRATEGY_MISSING_POLICIES[number]
export type StrategyField = 'name' | 'topic' | 'lookback_days' | 'signal_direction' | 'threshold_percent' | 'forecast_horizon_days' | 'predicted_outcome' | 'missing_data_policy'

export interface StrategySource {
  id: typeof STRATEGY_SOURCE_ID
  methodology_version: typeof STRATEGY_SOURCE_METHODOLOGY_VERSION
  project: 'en.wikipedia.org'
  access: 'all-access'
  agent: 'user'
  metric: 'daily_pageviews'
  topic: SupportedTopic
}

export interface StrategyDefinition {
  strategy_id: string
  schema_version: typeof STRATEGY_SCHEMA_VERSION
  name: string
  source: StrategySource
  observation_window: {
    unit: 'full_utc_days'
    comparison: 'previous_window_to_current_window'
    lookback_days: number
  }
  signal_direction: SignalDirection
  threshold_percent: number
  threshold_bps: number
  forecast_horizon_days: number
  predicted_outcome: PredictedOutcome
  missing_data_policy: MissingDataPolicy
  evaluation_methodology_version: typeof STRATEGY_EVALUATION_METHODOLOGY_VERSION
  evaluation: {
    signal_uses: 'previous_complete_window_and_current_complete_window_only'
    target_uses: 'following_complete_window_only'
    no_lookahead: true
  }
}

export interface StrategyDraft {
  name: string
  source_id: typeof STRATEGY_SOURCE_ID
  topic: SupportedTopic | null
  lookback_days: number | null
  signal_direction: SignalDirection | null
  threshold_percent: number | null
  forecast_horizon_days: number | null
  predicted_outcome: PredictedOutcome | null
  missing_data_policy: MissingDataPolicy | null
}

export interface StrategyValidationOk { ok: true; value: StrategyDefinition }
export interface StrategyValidationError { ok: false; errors: string[] }
export type StrategyValidation = StrategyValidationOk | StrategyValidationError

export type StrategyParseStatus = 'PARSED' | 'NEEDS_CONFIRMATION' | 'UNSUPPORTED'
export interface StrategyParseResult {
  status: StrategyParseStatus
  message: string
  normalized_input: string
  draft: StrategyDraft
  strategy: StrategyDefinition | null
  missing_fields: StrategyField[]
  unsupported_reasons: string[]
}

export interface CompiledStrategy {
  schema_version: typeof STRATEGY_SCHEMA_VERSION
  strategy_id: string
  source: StrategySource
  signal: {
    previous_window_days: number
    current_window_days: number
    direction: SignalDirection
    threshold_bps: number
  }
  target: {
    starts_after_signal_date: true
    horizon_days: number
    predicted_outcome: PredictedOutcome
  }
  missing_data_policy: MissingDataPolicy
  evaluation_methodology_version: typeof STRATEGY_EVALUATION_METHODOLOGY_VERSION
  guards: {
    complete_utc_days_only: true
    no_lookahead: true
  }
}

export interface StrategyDryRun {
  available: boolean
  reason: string | null
  dataset_id: string | null
  dataset_label: string | null
  candidate_dates: number
  signal_dates: number
  correct: number
  incorrect: number
  no_signal_dates: number
  unavailable_dates: number
  lookahead_safe: true
  decisions: Array<{
    signal_date: string
    momentum_bps: number
    threshold_bps: number
    prediction: PredictedOutcome
    outcome: PredictedOutcome
    correct: boolean
  }>
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

const FIELD_LABELS: Record<StrategyField, string> = {
  name: 'a strategy name',
  topic: 'a supported Wikimedia topic',
  lookback_days: 'the observation window',
  signal_direction: 'a signal direction',
  threshold_percent: 'a percentage threshold',
  forecast_horizon_days: 'a forecast horizon',
  predicted_outcome: 'a predicted outcome',
  missing_data_policy: 'a missing-data behavior',
}

export function emptyStrategyDraft(): StrategyDraft {
  return {
    name: '',
    source_id: STRATEGY_SOURCE_ID,
    topic: null,
    lookback_days: null,
    signal_direction: null,
    threshold_percent: null,
    forecast_horizon_days: null,
    predicted_outcome: null,
    missing_data_policy: null,
  }
}

function browserStorage(): StorageLike | null {
  if (typeof window === 'undefined') return null
  try { return window.localStorage } catch { return null }
}

function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, ' ')
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function topicForInput(input: string): { topic: SupportedTopic | null; unsupported?: string } {
  const candidates = SUPPORTED_TOPICS.flatMap((topic) => topic.aliases.map((alias) => ({ topic: topic.value, alias })))
    .sort((a, b) => b.alias.length - a.alias.length)
  for (const candidate of candidates) {
    if (new RegExp(`\\b${escapeRegExp(candidate.alias)}\\b`, 'i').test(input)) return { topic: candidate.topic }
  }
  const mentioned = input.match(/\b(?:if|when)\s+([a-z][a-z0-9 ._-]{1,40}?)\s+(?:attention|pageviews?|views?)\b/i)?.[1]
  return mentioned ? { topic: null, unsupported: `“${normalizeText(mentioned)}” is not one of the supported Wikimedia topics.` } : { topic: null }
}

function directionForInput(input: string): { value: SignalDirection | null; ambiguous: boolean } {
  const movementClause = input.split(/\b(?:predict|forecast|call|choose)\b/i, 1)[0]
  const rising = /\b(?:rise|rises|rising|increase|increases|increasing|grow|grows|growing|up|higher)\b/i.test(movementClause)
  const falling = /\b(?:fall|falls|falling|decrease|decreases|decreasing|drop|drops|dropping|down|lower)\b/i.test(movementClause)
  if (rising && falling) return { value: null, ambiguous: true }
  return { value: rising ? 'RISING' : falling ? 'FALLING' : null, ambiguous: false }
}

function numberAfter(pattern: RegExp, input: string): number | null {
  const value = input.match(pattern)?.[1]
  if (!value) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function missingPolicyForInput(input: string): MissingDataPolicy | null {
  const lower = input.toLowerCase()
  if (!lower.includes('missing') && !lower.includes('no data')) return null
  if (/\b(?:no signal|skip|do not signal|don't signal)\b/.test(lower)) return 'NO_SIGNAL'
  if (/\b(?:unavailable|mark.*unavailable)\b/.test(lower)) return 'UNAVAILABLE'
  return null
}

function defaultName(topic: SupportedTopic | null): string {
  return topic ? `${topic} attention strategy` : ''
}

export function parseStrategyIdea(input: string): StrategyParseResult {
  const normalized = normalizeText(input)
  const topicMatch = topicForInput(normalized)
  const directionMatch = directionForInput(normalized)
  const threshold = numberAfter(/(?:at\s+least|by|of)\s+(\d+(?:\.\d+)?)\s*%/i, normalized)
    ?? numberAfter(/(\d+(?:\.\d+)?)\s*%/, normalized)
  const lookback = numberAfter(/\b(?:previous|prior|last)\s+(\d+)\s+days?\b/i, normalized)
  const horizon = numberAfter(/\bnext\s+(\d+)\s+days?\b/i, normalized)
  const outcome = normalized.match(/\b(?:predict|forecast|call|choose)\s+(?:an?\s+)?(UP|DOWN)\b/i)?.[1]?.toUpperCase() as PredictedOutcome | undefined
  const missingPolicy = missingPolicyForInput(normalized)
  const unsupported: string[] = []

  if (/\b(?:price|market\s+cap|sentiment|twitter|reddit|social\s+media|probability|odds|wallet|trade|transaction|publish|execute)\b/i.test(normalized)) {
    unsupported.push('This builder only defines Wikimedia attention rules; price, sentiment, odds, wallet, trading, and execution language is unsupported.')
  }
  if (topicMatch.unsupported) unsupported.push(topicMatch.unsupported)
  if (directionMatch.ambiguous) unsupported.push('Use one signal direction: rising or falling.')
  if (lookback != null && !SUPPORTED_WINDOW_DAYS.includes(lookback as typeof SUPPORTED_WINDOW_DAYS[number])) {
    unsupported.push(`The observation window must be one of ${SUPPORTED_WINDOW_DAYS.join(', ')} days.`)
  }
  if (horizon != null && !SUPPORTED_WINDOW_DAYS.includes(horizon as typeof SUPPORTED_WINDOW_DAYS[number])) {
    unsupported.push(`The forecast horizon must be one of ${SUPPORTED_WINDOW_DAYS.join(', ')} days.`)
  }
  if (threshold != null && (threshold <= 0 || threshold > 1_000)) unsupported.push('The percentage threshold must be greater than 0% and no more than 1,000%.')

  const draft: StrategyDraft = {
    name: defaultName(topicMatch.topic),
    source_id: STRATEGY_SOURCE_ID,
    topic: topicMatch.topic,
    lookback_days: lookback,
    signal_direction: directionMatch.value,
    threshold_percent: threshold,
    forecast_horizon_days: horizon,
    predicted_outcome: outcome ?? null,
    missing_data_policy: missingPolicy,
  }
  const missing_fields = (Object.entries({
    topic: draft.topic,
    lookback_days: draft.lookback_days,
    signal_direction: draft.signal_direction,
    threshold_percent: draft.threshold_percent,
    forecast_horizon_days: draft.forecast_horizon_days,
    predicted_outcome: draft.predicted_outcome,
    missing_data_policy: draft.missing_data_policy,
  }) as Array<[StrategyField, unknown]>).filter(([, value]) => value == null).map(([field]) => field)

  if (unsupported.length) {
    return {
      status: 'UNSUPPORTED',
      message: unsupported.join(' '),
      normalized_input: normalized,
      draft,
      strategy: null,
      missing_fields,
      unsupported_reasons: unsupported,
    }
  }
  if (missing_fields.length) {
    const labels = missing_fields.map((field) => FIELD_LABELS[field])
    return {
      status: 'NEEDS_CONFIRMATION',
      message: `Parsed supported fields. Confirm ${labels.join(', ')} before saving; the parser will not guess them.`,
      normalized_input: normalized,
      draft,
      strategy: null,
      missing_fields,
      unsupported_reasons: [],
    }
  }
  const compiled = createStrategyFromDraft(draft)
  if (!compiled.ok) {
    return {
      status: 'UNSUPPORTED',
      message: compiled.errors.join(' '),
      normalized_input: normalized,
      draft,
      strategy: null,
      missing_fields: [],
      unsupported_reasons: compiled.errors,
    }
  }
  return {
    status: 'PARSED',
    message: 'Parsed without AI. Review the exact rule before saving.',
    normalized_input: normalized,
    draft,
    strategy: compiled.value,
    missing_fields: [],
    unsupported_reasons: [],
  }
}

function behaviorPayload(strategy: Pick<StrategyDefinition, 'source' | 'observation_window' | 'signal_direction' | 'threshold_bps' | 'forecast_horizon_days' | 'predicted_outcome' | 'missing_data_policy' | 'evaluation_methodology_version'>) {
  return {
    source: strategy.source,
    observation_window: strategy.observation_window,
    signal_direction: strategy.signal_direction,
    threshold_bps: strategy.threshold_bps,
    forecast_horizon_days: strategy.forecast_horizon_days,
    predicted_outcome: strategy.predicted_outcome,
    missing_data_policy: strategy.missing_data_policy,
    evaluation_methodology_version: strategy.evaluation_methodology_version,
  }
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(value)
}

function stableHash(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

function makeStrategyId(strategy: Pick<StrategyDefinition, 'source' | 'observation_window' | 'signal_direction' | 'threshold_bps' | 'forecast_horizon_days' | 'predicted_outcome' | 'missing_data_policy' | 'evaluation_methodology_version'>): string {
  return `strategy_${stableHash(canonicalJson(behaviorPayload(strategy)))}`
}

function sourceFor(topic: SupportedTopic): StrategySource {
  return {
    id: STRATEGY_SOURCE_ID,
    methodology_version: STRATEGY_SOURCE_METHODOLOGY_VERSION,
    project: 'en.wikipedia.org',
    access: 'all-access',
    agent: 'user',
    metric: 'daily_pageviews',
    topic,
  }
}

export function validateStrategy(value: unknown): StrategyValidation {
  const errors: string[] = []
  if (!value || typeof value !== 'object') return { ok: false, errors: ['A strategy object is required.'] }
  const row = value as Partial<StrategyDefinition>
  if (row.schema_version !== STRATEGY_SCHEMA_VERSION) errors.push(`schema_version must be ${STRATEGY_SCHEMA_VERSION}.`)
  if (typeof row.strategy_id !== 'string' || !/^strategy_[0-9a-f]{8}$/.test(row.strategy_id)) errors.push('strategy_id must be a generated versioned strategy id.')
  if (typeof row.name !== 'string' || normalizeText(row.name).length < 1 || normalizeText(row.name).length > 80) errors.push('name must contain 1-80 characters.')
  const source = row.source as Partial<StrategySource> | undefined
  if (!source || source.id !== STRATEGY_SOURCE_ID || source.methodology_version !== STRATEGY_SOURCE_METHODOLOGY_VERSION || source.project !== 'en.wikipedia.org' || source.access !== 'all-access' || source.agent !== 'user' || source.metric !== 'daily_pageviews') errors.push('source must use the supported Wikimedia Pageviews methodology.')
  if (!source || !SUPPORTED_TOPICS.some((topic) => topic.value === source.topic)) errors.push('source.topic must be one of the supported Wikimedia topics.')
  const window = row.observation_window as Partial<StrategyDefinition['observation_window']> | undefined
  if (!window || window.unit !== 'full_utc_days' || window.comparison !== 'previous_window_to_current_window' || !SUPPORTED_WINDOW_DAYS.includes(Number(window.lookback_days) as typeof SUPPORTED_WINDOW_DAYS[number])) errors.push(`observation_window must use one of ${SUPPORTED_WINDOW_DAYS.join(', ')} complete UTC days.`)
  if (row.signal_direction !== 'RISING' && row.signal_direction !== 'FALLING') errors.push('signal_direction must be RISING or FALLING.')
  if (typeof row.threshold_percent !== 'number' || !Number.isFinite(row.threshold_percent) || row.threshold_percent <= 0 || row.threshold_percent > 1_000) errors.push('threshold_percent must be greater than 0% and no more than 1,000%.')
  if (typeof row.threshold_bps !== 'number' || !Number.isSafeInteger(row.threshold_bps) || row.threshold_bps !== Math.round((row.threshold_percent ?? 0) * 100)) errors.push('threshold_bps must equal threshold_percent × 100.')
  if (!SUPPORTED_WINDOW_DAYS.includes(Number(row.forecast_horizon_days) as typeof SUPPORTED_WINDOW_DAYS[number])) errors.push(`forecast_horizon_days must be one of ${SUPPORTED_WINDOW_DAYS.join(', ')}.`)
  if (row.predicted_outcome !== 'UP' && row.predicted_outcome !== 'DOWN') errors.push('predicted_outcome must be UP or DOWN.')
  if (!STRATEGY_MISSING_POLICIES.includes(row.missing_data_policy as MissingDataPolicy)) errors.push('missing_data_policy must be NO_SIGNAL or UNAVAILABLE.')
  if (row.evaluation_methodology_version !== STRATEGY_EVALUATION_METHODOLOGY_VERSION) errors.push(`evaluation_methodology_version must be ${STRATEGY_EVALUATION_METHODOLOGY_VERSION}.`)
  const evaluation = row.evaluation as Partial<StrategyDefinition['evaluation']> | undefined
  if (!evaluation || evaluation.signal_uses !== 'previous_complete_window_and_current_complete_window_only' || evaluation.target_uses !== 'following_complete_window_only' || evaluation.no_lookahead !== true) errors.push('evaluation must declare complete windows and no lookahead.')
  if (errors.length) return { ok: false, errors }
  return { ok: true, value: row as StrategyDefinition }
}

export function createStrategyFromDraft(draft: StrategyDraft, options: { id?: string } = {}): StrategyValidation {
  const threshold = draft.threshold_percent
  const topic = draft.topic
  if (topic == null || draft.lookback_days == null || draft.signal_direction == null || threshold == null || draft.forecast_horizon_days == null || draft.predicted_outcome == null || draft.missing_data_policy == null) {
    return { ok: false, errors: ['Complete every strategy field before saving.'] }
  }
  const base = {
    source: sourceFor(topic),
    observation_window: {
      unit: 'full_utc_days' as const,
      comparison: 'previous_window_to_current_window' as const,
      lookback_days: draft.lookback_days,
    },
    signal_direction: draft.signal_direction,
    threshold_percent: threshold,
    threshold_bps: Math.round(threshold * 100),
    forecast_horizon_days: draft.forecast_horizon_days,
    predicted_outcome: draft.predicted_outcome,
    missing_data_policy: draft.missing_data_policy,
    evaluation_methodology_version: STRATEGY_EVALUATION_METHODOLOGY_VERSION as typeof STRATEGY_EVALUATION_METHODOLOGY_VERSION,
  }
  const strategy: StrategyDefinition = {
    strategy_id: options.id ?? makeStrategyId(base),
    schema_version: STRATEGY_SCHEMA_VERSION,
    name: normalizeText(draft.name) || defaultName(topic),
    ...base,
    evaluation: {
      signal_uses: 'previous_complete_window_and_current_complete_window_only',
      target_uses: 'following_complete_window_only',
      no_lookahead: true,
    },
  }
  return validateStrategy(strategy)
}

export function updateStrategy(strategy: StrategyDefinition, draft: StrategyDraft): StrategyValidation {
  return createStrategyFromDraft(draft, { id: strategy.strategy_id })
}

export function compileStrategy(strategy: StrategyDefinition): CompiledStrategy {
  const validation = validateStrategy(strategy)
  if (!validation.ok) throw new Error(validation.errors.join(' '))
  return {
    schema_version: STRATEGY_SCHEMA_VERSION,
    strategy_id: strategy.strategy_id,
    source: strategy.source,
    signal: {
      previous_window_days: strategy.observation_window.lookback_days,
      current_window_days: strategy.observation_window.lookback_days,
      direction: strategy.signal_direction,
      threshold_bps: strategy.threshold_bps,
    },
    target: {
      starts_after_signal_date: true,
      horizon_days: strategy.forecast_horizon_days,
      predicted_outcome: strategy.predicted_outcome,
    },
    missing_data_policy: strategy.missing_data_policy,
    evaluation_methodology_version: strategy.evaluation_methodology_version,
    guards: { complete_utc_days_only: true, no_lookahead: true },
  }
}

export function serializeStrategy(strategy: StrategyDefinition): string {
  const validation = validateStrategy(strategy)
  if (!validation.ok) throw new Error(validation.errors.join(' '))
  return JSON.stringify(validation.value, null, 2)
}

export function deserializeStrategy(serialized: string): StrategyValidation {
  try { return validateStrategy(JSON.parse(serialized)) } catch { return { ok: false, errors: ['Saved strategy JSON is invalid.'] } }
}

function parseDate(value: string): number {
  const parsed = Date.parse(`${value}T00:00:00Z`)
  if (!Number.isFinite(parsed)) throw new Error(`Invalid date: ${value}`)
  return parsed
}

function dateString(value: number): string { return new Date(value).toISOString().slice(0, 10) }
function dateRange(start: string, end: string): string[] {
  const rows: string[] = []
  for (let cursor = parseDate(start), finish = parseDate(end); cursor <= finish; cursor += 86_400_000) rows.push(dateString(cursor))
  return rows
}

export function dryRunStrategy(strategy: StrategyDefinition, dataset: HistoricalDataset): StrategyDryRun {
  const validation = validateStrategy(strategy)
  if (!validation.ok) return { available: false, reason: validation.errors.join(' '), dataset_id: null, dataset_label: null, candidate_dates: 0, signal_dates: 0, correct: 0, incorrect: 0, no_signal_dates: 0, unavailable_dates: 0, lookahead_safe: true, decisions: [] }
  const sameArticle = dataset.source.article.toLowerCase() === strategy.source.topic.toLowerCase()
  const sameMethodology = dataset.source.project === strategy.source.project && dataset.source.access === strategy.source.access && dataset.source.agent === strategy.source.agent && dataset.source.metric === strategy.source.metric
  if (!sameArticle || !sameMethodology) {
    return { available: false, reason: 'This frozen example dataset does not match the strategy topic and source.', dataset_id: dataset.dataset_id, dataset_label: dataset.label, candidate_dates: 0, signal_dates: 0, correct: 0, incorrect: 0, no_signal_dates: 0, unavailable_dates: 0, lookahead_safe: true, decisions: [] }
  }
  const values = new Map(dataset.observations.map((row) => [row.date, row.views]))
  const dates = [...values.keys()].sort()
  if (!dates.length) return { available: false, reason: 'The frozen example dataset has no observations.', dataset_id: dataset.dataset_id, dataset_label: dataset.label, candidate_dates: 0, signal_dates: 0, correct: 0, incorrect: 0, no_signal_dates: 0, unavailable_dates: 0, lookahead_safe: true, decisions: [] }
  const lookback = strategy.observation_window.lookback_days
  const horizon = strategy.forecast_horizon_days
  const first = shiftDay(dates[0], lookback * 2 - 1)
  const last = shiftDay(dates.at(-1)!, -horizon)
  const candidates = first <= last ? dateRange(first, last) : []
  const decisions: StrategyDryRun['decisions'] = []
  let noSignal = 0
  let unavailable = 0
  for (const signalDate of candidates) {
    const previous = dateRange(shiftDay(signalDate, -(lookback * 2 - 1)), shiftDay(signalDate, -lookback))
    const current = dateRange(shiftDay(signalDate, -(lookback - 1)), signalDate)
    const target = dateRange(shiftDay(signalDate, 1), shiftDay(signalDate, horizon))
    const required = [...previous, ...current, ...target]
    if (required.some((date) => !values.has(date) || !Number.isFinite(values.get(date)))) {
      if (strategy.missing_data_policy === 'NO_SIGNAL') noSignal += 1
      else unavailable += 1
      continue
    }
    const previousSum = previous.reduce((sum, date) => sum + values.get(date)!, 0)
    const currentSum = current.reduce((sum, date) => sum + values.get(date)!, 0)
    const momentum = growthBpsFromSums(previousSum, currentSum)
    const signaled = strategy.signal_direction === 'RISING' ? momentum >= strategy.threshold_bps : momentum <= -strategy.threshold_bps
    if (!signaled) { noSignal += 1; continue }
    const targetSum = target.reduce((sum, date) => sum + values.get(date)!, 0)
    const outcome: PredictedOutcome = targetSum >= currentSum ? 'UP' : 'DOWN'
    decisions.push({ signal_date: signalDate, momentum_bps: momentum, threshold_bps: strategy.threshold_bps, prediction: strategy.predicted_outcome, outcome, correct: strategy.predicted_outcome === outcome })
  }
  const correct = decisions.filter((decision) => decision.correct).length
  return {
    available: true,
    reason: null,
    dataset_id: dataset.dataset_id,
    dataset_label: dataset.label,
    candidate_dates: candidates.length,
    signal_dates: decisions.length,
    correct,
    incorrect: decisions.length - correct,
    no_signal_dates: noSignal,
    unavailable_dates: unavailable,
    lookahead_safe: true,
    decisions,
  }
}

export function explainStrategy(strategy: StrategyDefinition): { summary: string; trigger: string; evaluation: string[] } {
  const direction = strategy.signal_direction === 'RISING' ? 'at least' : 'at most'
  const sign = strategy.signal_direction === 'RISING' ? 'above' : 'below'
  return {
    summary: `Compare two adjacent ${strategy.observation_window.lookback_days}-day complete UTC windows for ${strategy.source.topic}.`,
    trigger: `Trigger when the current window is ${direction} ${strategy.threshold_percent}% ${sign} the previous window, then predict ${strategy.predicted_outcome} for the following ${strategy.forecast_horizon_days} complete UTC days.`,
    evaluation: [
      `Source: ${strategy.source.project} ${strategy.source.metric} for ${strategy.source.topic}.`,
      `Missing data: ${strategy.missing_data_policy === 'NO_SIGNAL' ? 'skip the signal' : 'mark the date unavailable'}; no values are imputed.`,
      'The signal reads only complete windows ending on the decision date. The target window begins afterward, so no future observation can influence the signal.',
    ],
  }
}

export function draftFromStrategy(strategy: StrategyDefinition): StrategyDraft {
  return {
    name: strategy.name,
    source_id: strategy.source.id,
    topic: strategy.source.topic,
    lookback_days: strategy.observation_window.lookback_days,
    signal_direction: strategy.signal_direction,
    threshold_percent: strategy.threshold_percent,
    forecast_horizon_days: strategy.forecast_horizon_days,
    predicted_outcome: strategy.predicted_outcome,
    missing_data_policy: strategy.missing_data_policy,
  }
}

export function draftToSentence(draft: StrategyDraft): string {
  const topic = draft.topic ?? '[topic]'
  const direction = draft.signal_direction === 'FALLING' ? 'falls' : draft.signal_direction === 'RISING' ? 'rises' : '[rises or falls]'
  const threshold = draft.threshold_percent == null ? '[threshold]%' : `${draft.threshold_percent}%`
  const lookback = draft.lookback_days == null ? '[window]' : `${draft.lookback_days} days`
  const outcome = draft.predicted_outcome ?? '[UP or DOWN]'
  const horizon = draft.forecast_horizon_days == null ? '[horizon]' : `${draft.forecast_horizon_days} days`
  const missing = draft.missing_data_policy === 'NO_SIGNAL' ? ' If data is missing, do not signal.' : draft.missing_data_policy === 'UNAVAILABLE' ? ' If data is missing, mark the date unavailable.' : ''
  return `If ${topic} attention ${direction} by at least ${threshold} over the previous ${lookback}, predict ${outcome} for the next ${horizon}.${missing}`
}

export function readStrategies(storage: StorageLike | null = browserStorage()): StrategyDefinition[] {
  if (!storage) return []
  try {
    const raw = JSON.parse(storage.getItem(STRATEGY_STORAGE_KEY) ?? 'null') as { version?: unknown; strategies?: unknown } | null
    if (!raw || raw.version !== STRATEGY_STORAGE_VERSION || !Array.isArray(raw.strategies)) return []
    return raw.strategies.flatMap((item) => {
      const validation = validateStrategy(item)
      return validation.ok ? [validation.value] : []
    })
  } catch { return [] }
}

export function writeStrategies(strategies: StrategyDefinition[], storage: StorageLike | null = browserStorage()): boolean {
  if (!storage) return false
  try {
    const valid = strategies.flatMap((strategy) => {
      const validation = validateStrategy(strategy)
      return validation.ok ? [validation.value] : []
    })
    storage.setItem(STRATEGY_STORAGE_KEY, JSON.stringify({ version: STRATEGY_STORAGE_VERSION, strategies: valid }))
    return true
  } catch { return false }
}

export function upsertStrategy(strategy: StrategyDefinition, storage: StorageLike | null = browserStorage()): boolean {
  const current = readStrategies(storage).filter((item) => item.strategy_id !== strategy.strategy_id)
  return writeStrategies([strategy, ...current], storage)
}

export function removeStrategy(strategyId: string, storage: StorageLike | null = browserStorage()): boolean {
  return writeStrategies(readStrategies(storage).filter((strategy) => strategy.strategy_id !== strategyId), storage)
}

export function structuredStrategyPayload(strategy: StrategyDefinition): Record<string, unknown> {
  const validation = validateStrategy(strategy)
  if (!validation.ok) throw new Error(validation.errors.join(' '))
  return JSON.parse(serializeStrategy(validation.value)) as Record<string, unknown>
}

export function strategyFieldLabel(field: StrategyField): string { return FIELD_LABELS[field] }

export function supportedTopic(value: string): value is SupportedTopic {
  return SUPPORTED_TOPICS.some((topic) => topic.value === value)
}
