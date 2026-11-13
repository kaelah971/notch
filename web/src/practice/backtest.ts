export const LOOKBACK_DAYS = 7
export const FORWARD_DAYS = 7
export const DEFAULT_MOMENTUM_THRESHOLD_BPS = 500
export const MOMENTUM_THRESHOLDS_BPS = [0, 500, 1_000, 1_500, 2_000] as const
export const STRATEGY_NAME = 'Seven-day attention momentum'
export const BASELINE_NAME = 'Always UP on the same signal dates'

export interface HistoricalObservation {
  date: string
  views: number
}

export interface HistoricalDataset {
  dataset_id: string
  version: number
  label: string
  source: {
    provider: string
    project: string
    article: string
    access: string
    agent: string
    metric: string
    url: string
  }
  observation_start: string
  observation_end: string
  retrieval_provenance: {
    recorded_fixture: string
    source_fixture_sha256: string
    fixture_manifest_fetched_at: string
    subset_rule: string
  }
  observations: ReadonlyArray<HistoricalObservation>
  content_sha256: string
}

export interface ReplayConfig {
  momentum_threshold_bps: number
}

export interface ReplayWindow {
  start: string
  end: string
  sum_views: number
  average_views: number
}

export interface ReplayDecision {
  signal_date: string
  previous_window: ReplayWindow
  signal_window: ReplayWindow
  target_window: ReplayWindow
  momentum_bps: number
  threshold_bps: number
  prediction: 'UP' | 'DOWN'
  outcome: 'UP' | 'DOWN'
  correct: boolean
}

export interface ReplayUnavailable {
  signal_date: string
  missing_dates: string[]
}

export interface ReplayBaseline {
  name: string
  evaluated_signals: number
  correct: number
  incorrect: number
  accuracy: number | null
}

export interface ReplayResult {
  dataset_id: string
  strategy_name: string
  threshold_bps: number
  lookback_days: number
  forward_days: number
  candidate_dates: number
  evaluated_signals: number
  correct: number
  incorrect: number
  accuracy: number | null
  no_signal_dates: number
  unavailable_dates: number
  unavailable: ReplayUnavailable[]
  decisions: ReplayDecision[]
  baseline: ReplayBaseline
}

export function canonicalFixturePayload(dataset: HistoricalDataset) {
  return {
    dataset_id: dataset.dataset_id,
    version: dataset.version,
    label: dataset.label,
    source: dataset.source,
    observation_start: dataset.observation_start,
    observation_end: dataset.observation_end,
    retrieval_provenance: dataset.retrieval_provenance,
    observations: dataset.observations,
  }
}

function parseDay(value: string): number {
  const timestamp = Date.parse(`${value}T00:00:00Z`)
  if (!Number.isFinite(timestamp)) throw new Error(`Invalid historical observation date: ${value}`)
  return timestamp
}

function dayString(timestamp: number): string {
  return new Date(timestamp).toISOString().slice(0, 10)
}

export function shiftDay(value: string, offset: number): string {
  return dayString(parseDay(value) + offset * 86_400_000)
}

function dateRange(start: string, end: string): string[] {
  const days: string[] = []
  for (let cursor = parseDay(start), finish = parseDay(end); cursor <= finish; cursor += 86_400_000) days.push(dayString(cursor))
  return days
}

function floorDivide(numerator: bigint, denominator: bigint): bigint {
  if (numerator >= 0n) return numerator / denominator
  return -((-numerator + denominator - 1n) / denominator)
}

export function growthBpsFromSums(previousSum: number, signalSum: number): number {
  if (!Number.isSafeInteger(previousSum) || previousSum <= 0) throw new Error('The previous historical window must have positive integer views.')
  if (!Number.isSafeInteger(signalSum) || signalSum < 0) throw new Error('The signal historical window must have non-negative integer views.')
  return Number(floorDivide((BigInt(signalSum) - BigInt(previousSum)) * 10_000n, BigInt(previousSum)))
}

function average(sum: number, count: number): number {
  return Math.floor(sum / count)
}

function windowFor(dates: string[], values: Map<string, number>): ReplayWindow {
  const sum = dates.reduce((total, date) => total + (values.get(date) ?? 0), 0)
  return { start: dates[0], end: dates.at(-1)!, sum_views: sum, average_views: average(sum, dates.length) }
}

function accuracy(correct: number, evaluated: number): number | null {
  return evaluated ? correct / evaluated * 100 : null
}

function predictionForMomentum(momentumBps: number, thresholdBps: number): 'UP' | 'DOWN' | null {
  if (thresholdBps === 0) {
    if (momentumBps > 0) return 'UP'
    if (momentumBps < 0) return 'DOWN'
    return null
  }
  if (momentumBps >= thresholdBps) return 'UP'
  if (momentumBps <= -thresholdBps) return 'DOWN'
  return null
}

function validateThreshold(thresholdBps: number): void {
  if (!Number.isInteger(thresholdBps) || !MOMENTUM_THRESHOLDS_BPS.includes(thresholdBps as typeof MOMENTUM_THRESHOLDS_BPS[number])) {
    throw new Error(`Threshold must be one of ${MOMENTUM_THRESHOLDS_BPS.join(', ')} bps.`)
  }
}

function observationMap(dataset: HistoricalDataset): Map<string, number> {
  const values = new Map<string, number>()
  for (const observation of dataset.observations) {
    parseDay(observation.date)
    if (!Number.isSafeInteger(observation.views) || observation.views < 0) throw new Error(`Invalid historical views for ${observation.date}.`)
    if (values.has(observation.date)) throw new Error(`Duplicate historical observation for ${observation.date}.`)
    values.set(observation.date, observation.views)
  }
  return values
}

export function runBacktest(dataset: HistoricalDataset, config: ReplayConfig = { momentum_threshold_bps: DEFAULT_MOMENTUM_THRESHOLD_BPS }): ReplayResult {
  validateThreshold(config.momentum_threshold_bps)
  const values = observationMap(dataset)
  const dates = [...values.keys()].sort()
  const firstCandidate = dates.length ? shiftDay(dates[0], LOOKBACK_DAYS * 2 - 1) : ''
  const lastCandidate = dates.length ? shiftDay(dates.at(-1)!, -FORWARD_DAYS) : ''
  const candidates = firstCandidate && lastCandidate && firstCandidate <= lastCandidate ? dateRange(firstCandidate, lastCandidate) : []
  const decisions: ReplayDecision[] = []
  const unavailable: ReplayUnavailable[] = []
  let noSignalDates = 0

  for (const signalDate of candidates) {
    const previousDates = dateRange(shiftDay(signalDate, -(LOOKBACK_DAYS * 2 - 1)), shiftDay(signalDate, -LOOKBACK_DAYS))
    const signalDates = dateRange(shiftDay(signalDate, -(LOOKBACK_DAYS - 1)), signalDate)
    const targetDates = dateRange(shiftDay(signalDate, 1), shiftDay(signalDate, FORWARD_DAYS))
    const required = [...previousDates, ...signalDates, ...targetDates]
    const missingDates = required.filter((date) => !values.has(date))
    if (missingDates.length) {
      unavailable.push({ signal_date: signalDate, missing_dates: [...new Set(missingDates)] })
      continue
    }
    const previousWindow = windowFor(previousDates, values)
    const signalWindow = windowFor(signalDates, values)
    const targetWindow = windowFor(targetDates, values)
    const momentumBps = growthBpsFromSums(previousWindow.sum_views, signalWindow.sum_views)
    const prediction = predictionForMomentum(momentumBps, config.momentum_threshold_bps)
    if (!prediction) {
      noSignalDates += 1
      continue
    }
    const outcome = targetWindow.sum_views >= signalWindow.sum_views ? 'UP' : 'DOWN'
    decisions.push({
      signal_date: signalDate,
      previous_window: previousWindow,
      signal_window: signalWindow,
      target_window: targetWindow,
      momentum_bps: momentumBps,
      threshold_bps: config.momentum_threshold_bps,
      prediction,
      outcome,
      correct: prediction === outcome,
    })
  }

  const correct = decisions.filter((decision) => decision.correct).length
  const baselineCorrect = decisions.filter((decision) => decision.outcome === 'UP').length
  return {
    dataset_id: dataset.dataset_id,
    strategy_name: STRATEGY_NAME,
    threshold_bps: config.momentum_threshold_bps,
    lookback_days: LOOKBACK_DAYS,
    forward_days: FORWARD_DAYS,
    candidate_dates: candidates.length,
    evaluated_signals: decisions.length,
    correct,
    incorrect: decisions.length - correct,
    accuracy: accuracy(correct, decisions.length),
    no_signal_dates: noSignalDates,
    unavailable_dates: unavailable.length,
    unavailable,
    decisions,
    baseline: {
      name: BASELINE_NAME,
      evaluated_signals: decisions.length,
      correct: baselineCorrect,
      incorrect: decisions.length - baselineCorrect,
      accuracy: accuracy(baselineCorrect, decisions.length),
    },
  }
}
