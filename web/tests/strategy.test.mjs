import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { NVIDIA_MOMENTUM_DATASET } from '../src/practice/fixtures/nvidia-momentum-v1.ts'
import {
  STRATEGY_SCHEMA_VERSION,
  STRATEGY_SOURCE_ID,
  createStrategyFromDraft,
  draftToSentence,
  dryRunStrategy,
  deserializeStrategy,
  emptyStrategyDraft,
  parseStrategyIdea,
  readStrategies,
  removeStrategy,
  serializeStrategy,
  compileStrategy,
  updateStrategy,
  upsertStrategy,
  validateStrategy,
} from '../src/strategy/strategy.ts'

class MemoryStorage {
  values = new Map()
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null }
  setItem(key, value) { this.values.set(key, String(value)) }
}

function completeDraft(overrides = {}) {
  return {
    ...emptyStrategyDraft(),
    name: 'Nvidia attention momentum',
    source_id: STRATEGY_SOURCE_ID,
    topic: 'Nvidia',
    lookback_days: 7,
    signal_direction: 'RISING',
    threshold_percent: 10,
    forecast_horizon_days: 7,
    predicted_outcome: 'UP',
    missing_data_policy: 'NO_SIGNAL',
    ...overrides,
  }
}

test('supported natural-language patterns compile to the versioned schema', () => {
  const result = parseStrategyIdea('If NVIDIA attention rises by at least 10% over the previous 7 days, predict UP for the next 7 days. If data is missing, do not signal.')
  assert.equal(result.status, 'PARSED')
  assert.equal(result.strategy?.schema_version, STRATEGY_SCHEMA_VERSION)
  assert.equal(result.strategy?.source.topic, 'Nvidia')
  assert.equal(result.strategy?.signal_direction, 'RISING')
  assert.equal(result.strategy?.threshold_bps, 1000)
  assert.equal(result.strategy?.forecast_horizon_days, 7)
  assert.equal(result.strategy?.missing_data_policy, 'NO_SIGNAL')

  const falling = parseStrategyIdea('When BTC attention falls by 2.5% over the previous 3 days, forecast DOWN for the next 14 days. If missing data is unavailable, mark unavailable.')
  assert.equal(falling.status, 'PARSED')
  assert.equal(falling.strategy?.source.topic, 'Bitcoin')
  assert.equal(falling.strategy?.signal_direction, 'FALLING')
  assert.equal(falling.strategy?.threshold_percent, 2.5)
  assert.equal(falling.strategy?.observation_window.lookback_days, 3)
  assert.equal(falling.strategy?.forecast_horizon_days, 14)
  assert.equal(falling.strategy?.missing_data_policy, 'UNAVAILABLE')

  const fallingUp = parseStrategyIdea('If BTC attention falls by 2.5% over the previous 3 days, predict UP for the next 14 days. If data is missing, do not signal.')
  assert.equal(fallingUp.status, 'PARSED')
  assert.equal(fallingUp.strategy?.signal_direction, 'FALLING')
  assert.equal(fallingUp.strategy?.predicted_outcome, 'UP')
})

test('missing critical language is shown for confirmation instead of guessed', () => {
  const result = parseStrategyIdea('If NVIDIA attention rises by at least 10% over the previous 7 days, predict UP for the next 7 days.')
  assert.equal(result.status, 'NEEDS_CONFIRMATION')
  assert.ok(result.missing_fields.includes('missing_data_policy'))
  assert.equal(result.strategy, null)
})

test('unsupported sources, topics, combinations, and horizons are honest', () => {
  const price = parseStrategyIdea('If Ethereum price rises by 10%, predict UP next week.')
  assert.equal(price.status, 'UNSUPPORTED')
  assert.match(price.message, /only defines Wikimedia attention/i)

  const invalidHorizon = parseStrategyIdea('If NVIDIA attention rises by 10% over the previous 7 days, predict UP for the next 2 days. If missing data, no signal.')
  assert.equal(invalidHorizon.status, 'UNSUPPORTED')
  assert.match(invalidHorizon.message, /forecast horizon/i)

  const invalid = createStrategyFromDraft(completeDraft({ forecast_horizon_days: 2 }))
  assert.equal(invalid.ok, false)
  if (!invalid.ok) assert.match(invalid.errors.join(' '), /forecast_horizon_days/)
})

test('threshold boundaries and schema validation are explicit', () => {
  const lower = createStrategyFromDraft(completeDraft({ threshold_percent: 0 }))
  assert.equal(lower.ok, false)
  const upper = createStrategyFromDraft(completeDraft({ threshold_percent: 1000 }))
  assert.equal(upper.ok, true)
  if (!upper.ok) return
  const mismatch = validateStrategy({ ...upper.value, threshold_bps: 999 })
  assert.equal(mismatch.ok, false)
  assert.deepEqual(compileStrategy(upper.value).guards, { complete_utc_days_only: true, no_lookahead: true })
})

test('equivalent supported inputs have identical serialized behavior', () => {
  const first = parseStrategyIdea('If NVIDIA attention rises by at least 10% over the previous 7 days, predict UP for the next 7 days. If data is missing, do not signal.')
  const second = parseStrategyIdea('If nvda attention increases by 10% over the prior 7 days, forecast UP for the next 7 days. If no data, skip the signal.')
  assert.equal(first.status, 'PARSED')
  assert.equal(second.status, 'PARSED')
  assert.equal(serializeStrategy(first.strategy), serializeStrategy(second.strategy))
  assert.deepEqual(compileStrategy(first.strategy), compileStrategy(second.strategy))
  assert.equal(draftToSentence(first.strategy && {
    ...completeDraft(),
    topic: first.strategy.source.topic,
    lookback_days: first.strategy.observation_window.lookback_days,
    signal_direction: first.strategy.signal_direction,
    threshold_percent: first.strategy.threshold_percent,
    forecast_horizon_days: first.strategy.forecast_horizon_days,
    predicted_outcome: first.strategy.predicted_outcome,
    missing_data_policy: first.strategy.missing_data_policy,
  }), 'If Nvidia attention rises by at least 10% over the previous 7 days, predict UP for the next 7 days. If data is missing, do not signal.')
})

test('local persistence saves, reloads, updates, and deletes versioned strategies', () => {
  const storage = new MemoryStorage()
  const created = createStrategyFromDraft(completeDraft())
  assert.equal(created.ok, true)
  if (!created.ok) return
  assert.equal(upsertStrategy(created.value, storage), true)
  assert.equal(readStrategies(storage)[0].strategy_id, created.value.strategy_id)
  assert.deepEqual(deserializeStrategy(serializeStrategy(created.value)), { ok: true, value: created.value })
  assert.equal(deserializeStrategy('{"schema_version":"old"}').ok, false)
  const changed = updateStrategy(created.value, completeDraft({ name: 'Renamed local rule', threshold_percent: 12 }))
  assert.equal(changed.ok, true)
  if (!changed.ok) return
  assert.equal(upsertStrategy(changed.value, storage), true)
  assert.equal(readStrategies(storage)[0].name, 'Renamed local rule')
  assert.equal(removeStrategy(changed.value.strategy_id, storage), true)
  assert.deepEqual(readStrategies(storage), [])
})

test('Scout-style prefill remains supported and dry-run does not look ahead', () => {
  const strategy = createStrategyFromDraft(completeDraft())
  assert.equal(strategy.ok, true)
  if (!strategy.ok) return
  const original = dryRunStrategy(strategy.value, NVIDIA_MOMENTUM_DATASET)
  assert.equal(original.available, true)
  assert.equal(original.lookahead_safe, true)
  assert.ok(original.signal_dates > 0)

  const targetChanged = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date >= '2026-11-04' ? { ...row, views: 0 } : row),
  }
  const changed = dryRunStrategy(strategy.value, targetChanged)
  assert.equal(changed.available, true)
  assert.deepEqual(
    changed.decisions.map(({ signal_date, momentum_bps, prediction }) => ({ signal_date, momentum_bps, prediction })),
    original.decisions.map(({ signal_date, momentum_bps, prediction }) => ({ signal_date, momentum_bps, prediction })),
  )

  const missingTarget = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date === '2026-10-28' ? { ...row, views: null } : row),
  }
  const noSignal = dryRunStrategy(strategy.value, missingTarget)
  assert.equal(noSignal.unavailable_dates, 0)
  assert.ok(noSignal.no_signal_dates > original.no_signal_dates)
  const unavailableStrategy = createStrategyFromDraft(completeDraft({ missing_data_policy: 'UNAVAILABLE' }))
  assert.equal(unavailableStrategy.ok, true)
  if (!unavailableStrategy.ok) return
  const unavailable = dryRunStrategy(unavailableStrategy.value, missingTarget)
  assert.ok(unavailable.unavailable_dates > 0)
})

test('strategy builder has no wallet, signing, entry, or transaction path', () => {
  const source = readFileSync(new URL('../src/pages/StrategyBuilder.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /entryIntent|wallet|signer|transaction|ft_transfer_call/i)
})
