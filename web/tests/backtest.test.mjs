import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { NVIDIA_MOMENTUM_DATASET } from '../src/practice/fixtures/nvidia-momentum-v1.ts'
import { canonicalFixturePayload, growthBpsFromSums, runBacktest } from '../src/practice/backtest.ts'

const hash = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex')

const syntheticDataset = (views) => ({
  ...NVIDIA_MOMENTUM_DATASET,
  dataset_id: 'test-demo-boundary-fixture',
  observations: views.map((value, index) => ({ date: `2026-01-${String(index + 1).padStart(2, '0')}`, views: value })),
})

test('frozen Wikimedia fixture integrity is reproducible and the default replay is deterministic', () => {
  const sourcePath = fileURLToPath(new URL('../../services/oracle/fixtures/pageviews_Nvidia.json', import.meta.url))
  const sourceBytes = readFileSync(sourcePath)
  const source = JSON.parse(sourceBytes.toString())
  const sourceSubset = source.items
    .filter((item) => item.timestamp >= '2026100100' && item.timestamp <= '2026111000')
    .map((item) => ({ date: `${item.timestamp.slice(0, 4)}-${item.timestamp.slice(4, 6)}-${item.timestamp.slice(6, 8)}`, views: item.views }))
  assert.equal(createHash('sha256').update(sourceBytes).digest('hex'), NVIDIA_MOMENTUM_DATASET.retrieval_provenance.source_fixture_sha256)
  assert.deepEqual(NVIDIA_MOMENTUM_DATASET.observations, sourceSubset)
  assert.equal(hash(canonicalFixturePayload(NVIDIA_MOMENTUM_DATASET)), NVIDIA_MOMENTUM_DATASET.content_sha256)
  const first = runBacktest(NVIDIA_MOMENTUM_DATASET, { momentum_threshold_bps: 500 })
  const second = runBacktest(NVIDIA_MOMENTUM_DATASET, { momentum_threshold_bps: 500 })
  assert.deepEqual(second, first)
  assert.equal(first.candidate_dates, 21)
  assert.equal(first.evaluated_signals, 16)
  assert.equal(first.correct, 7)
  assert.equal(first.incorrect, 9)
  assert.equal(first.accuracy, 43.75)
  assert.equal(first.baseline.correct, 5)
  assert.equal(first.baseline.accuracy, 31.25)
})

test('replay never uses target-window observations to generate a signal', () => {
  const result = runBacktest(NVIDIA_MOMENTUM_DATASET, { momentum_threshold_bps: 500 })
  assert.ok(result.decisions.length > 0)
  for (const decision of result.decisions) {
    assert.ok(decision.previous_window.end <= decision.signal_date)
    assert.ok(decision.signal_window.end <= decision.signal_date)
    assert.ok(decision.target_window.start > decision.signal_date)
    assert.equal(decision.target_window.end > decision.signal_date, true)
  }
})

test('missing observations are reported as unavailable instead of guessed', () => {
  const missing = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.filter((observation) => observation.date !== '2026-10-20'),
  }
  const result = runBacktest(missing, { momentum_threshold_bps: 500 })
  assert.ok(result.unavailable_dates > 0)
  assert.ok(result.unavailable.some((row) => row.missing_dates.includes('2026-10-20')))
})

test('threshold boundaries and zero-sample behavior are explicit', () => {
  assert.equal(growthBpsFromSums(700, 735), 500)
  const boundary = runBacktest(syntheticDataset([
    100, 100, 100, 100, 100, 100, 100,
    105, 105, 105, 105, 105, 105, 105,
    100, 100, 100, 100, 100, 100, 100,
  ]), { momentum_threshold_bps: 500 })
  assert.equal(boundary.evaluated_signals, 1)
  assert.equal(boundary.decisions[0].momentum_bps, 500)
  assert.equal(boundary.decisions[0].prediction, 'UP')
  assert.equal(boundary.decisions[0].outcome, 'DOWN')
  const zero = runBacktest(NVIDIA_MOMENTUM_DATASET, { momentum_threshold_bps: 2_000 })
  assert.equal(zero.evaluated_signals, 0)
  assert.equal(zero.accuracy, null)
  assert.equal(zero.baseline.accuracy, null)
})

test('Practice page has no wallet signer or entry-intent dependency', () => {
  const source = readFileSync(fileURLToPath(new URL('../src/pages/Practice.tsx', import.meta.url)), 'utf8')
  assert.doesNotMatch(source, /signAndSend|entryIntent|sendTransaction/)
})
