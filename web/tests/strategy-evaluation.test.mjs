import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { NVIDIA_MOMENTUM_DATASET } from '../src/practice/fixtures/nvidia-momentum-v1.ts'
import {
  STRATEGY_SOURCE_ID,
  canonicalStrategyHash,
  compareStrategies,
  createStrategyFromDraft,
  emptyStrategyDraft,
  evaluateStrategy,
  updateStrategy,
} from '../src/strategy/strategy.ts'

function draft(overrides = {}) {
  return {
    ...emptyStrategyDraft(),
    name: 'Nvidia evaluation rule',
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

function strategy(overrides = {}) {
  const result = createStrategyFromDraft(draft(overrides))
  assert.equal(result.ok, true)
  if (!result.ok) throw new Error(result.errors.join(' '))
  return result.value
}

test('evaluation is deterministic and exposes provenance and a result digest', () => {
  const rule = strategy()
  const first = evaluateStrategy(rule, NVIDIA_MOMENTUM_DATASET)
  const second = evaluateStrategy(rule, NVIDIA_MOMENTUM_DATASET)
  assert.deepEqual(second, first)
  assert.equal(first.status, 'EVALUATED')
  assert.equal(first.strategy_hash, canonicalStrategyHash(rule))
  assert.equal(first.schema_version, 'notch.strategy/1')
  assert.equal(first.evaluation_methodology_version, 'notch-historical-evaluation/1')
  assert.equal(first.dataset_content_sha256, NVIDIA_MOMENTUM_DATASET.content_sha256)
  assert.match(first.result_digest, /^fnv1a32:/)
  assert.equal(first.lookahead_safe, true)
})

test('signal decisions never change when only the later target window changes', () => {
  const rule = strategy()
  const original = evaluateStrategy(rule, NVIDIA_MOMENTUM_DATASET)
  const targetChanged = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date >= '2026-11-04' ? { ...row, views: 0 } : row),
  }
  const changed = evaluateStrategy(rule, targetChanged)
  assert.equal(changed.status, 'EVALUATED')
  assert.deepEqual(
    changed.decisions.map(({ signal_date, momentum_bps, threshold_bps, prediction }) => ({ signal_date, momentum_bps, threshold_bps, prediction })),
    original.decisions.map(({ signal_date, momentum_bps, threshold_bps, prediction }) => ({ signal_date, momentum_bps, threshold_bps, prediction })),
  )
})

test('threshold boundaries and no-signal evaluation remain explicit', () => {
  const inclusive = evaluateStrategy(strategy({ threshold_percent: 12.17 }), NVIDIA_MOMENTUM_DATASET)
  const exclusive = evaluateStrategy(strategy({ threshold_percent: 12.18 }), NVIDIA_MOMENTUM_DATASET)
  assert.equal(inclusive.status, 'EVALUATED')
  assert.equal(exclusive.status, 'EVALUATED')
  assert.ok(inclusive.decisions.some((decision) => decision.signal_date === '2026-10-21'))
  assert.ok(!exclusive.decisions.some((decision) => decision.signal_date === '2026-10-21'))

  const none = evaluateStrategy(strategy({ threshold_percent: 1000 }), NVIDIA_MOMENTUM_DATASET)
  assert.equal(none.status, 'EVALUATED')
  assert.equal(none.triggered_signals, 0)
  assert.equal(none.accuracy, null)
  assert.equal(none.baseline.accuracy, null)
  assert.equal(none.skipped_windows, none.eligible_windows)
})

test('missing and zero-valued observations are never imputed', () => {
  const missing = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date === '2026-10-21' ? { ...row, views: null } : row),
  }
  const missingResult = evaluateStrategy(strategy(), missing)
  assert.equal(missingResult.status, 'EVALUATED')
  assert.ok(missingResult.missing_windows > 0)
  assert.ok(missingResult.unavailable.some((row) => row.reason === 'MISSING_OBSERVATIONS'))

  const zeroBaseline = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date <= '2026-10-07' ? { ...row, views: 0 } : row),
  }
  const zeroResult = evaluateStrategy(strategy(), zeroBaseline)
  assert.equal(zeroResult.status, 'EVALUATED')
  assert.ok(zeroResult.zero_baseline_windows > 0)
  assert.ok(zeroResult.unavailable.some((row) => row.reason === 'ZERO_BASELINE'))
})

test('unsupported topics and insufficient horizons have honest states', () => {
  const unsupported = evaluateStrategy(strategy({ topic: 'ChatGPT' }), NVIDIA_MOMENTUM_DATASET)
  assert.equal(unsupported.status, 'UNSUPPORTED')
  assert.match(unsupported.reason, /No genuine frozen Wikimedia dataset/i)
  assert.match(unsupported.result_digest, /^fnv1a32:/)

  const tooLong = evaluateStrategy(strategy({ forecast_horizon_days: 30 }), NVIDIA_MOMENTUM_DATASET)
  assert.equal(tooLong.status, 'INSUFFICIENT_DATA')
  assert.match(tooLong.reason, /too short/i)
  assert.match(tooLong.result_digest, /^fnv1a32:/)
})

test('Always-UP baseline is aligned to the strategy signal population', () => {
  const result = evaluateStrategy(strategy(), NVIDIA_MOMENTUM_DATASET)
  assert.equal(result.status, 'EVALUATED')
  const alwaysUpCorrect = result.decisions.filter((decision) => decision.outcome === 'UP').length
  assert.equal(result.baseline.evaluated_signals, result.triggered_signals)
  assert.equal(result.baseline.correct, alwaysUpCorrect)
  assert.equal(result.baseline.incorrect, result.triggered_signals - alwaysUpCorrect)
  assert.equal(result.baseline.percentage_point_difference, result.accuracy - result.baseline.accuracy)
})

test('comparison discloses coverage differences and overlapping windows', () => {
  const first = strategy({ name: 'Lower threshold', threshold_percent: 10 })
  const second = strategy({ name: 'Higher threshold', threshold_percent: 15 })
  const comparison = compareStrategies(first, second, NVIDIA_MOMENTUM_DATASET)
  assert.equal(comparison.available, true)
  assert.equal(comparison.same_eligible_population, true)
  assert.equal(comparison.same_signal_population, false)
  assert.ok(comparison.matched_eligible_windows > 0)
  assert.ok(comparison.warnings.some((warning) => /coverage differs/i.test(warning)))
  assert.ok(comparison.warnings.some((warning) => /overlap/i.test(warning)))
})

test('evaluation lab has no wallet, signing, transaction, or AI execution path', () => {
  const source = readFileSync(new URL('../src/pages/StrategyLab.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /WalletProvider|useWallet|entryIntent|ft_transfer_call|api\./i)
})

test('strategy identity stays stable while edited revisions receive different hashes', () => {
  const original = strategy({ name: 'Original name' })
  const edited = updateStrategy(original, draft({ name: 'Edited name', threshold_percent: 12 }))
  assert.equal(edited.ok, true)
  if (!edited.ok) return
  assert.equal(edited.value.strategy_id, original.strategy_id)
  assert.notEqual(canonicalStrategyHash(edited.value), canonicalStrategyHash(original))
  assert.equal(evaluateStrategy(edited.value, NVIDIA_MOMENTUM_DATASET).strategy_hash, canonicalStrategyHash(edited.value))
})
