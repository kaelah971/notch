import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { NVIDIA_MOMENTUM_DATASET } from '../src/practice/fixtures/nvidia-momentum-v1.ts'
import {
  ARENA_DEFAULT_RISK_POLICY,
  arenaParticipants,
  builtInArenaParticipants,
  isArenaCompatible,
  runArenaMatch,
} from '../src/arena/arena.ts'
import { createStrategyFromDraft, emptyStrategyDraft } from '../src/strategy/strategy.ts'

function strategy(overrides = {}) {
  const result = createStrategyFromDraft({
    ...emptyStrategyDraft(),
    name: 'Saved arena rule',
    source_id: 'wikimedia-pageviews-v1',
    topic: 'Nvidia',
    lookback_days: 7,
    signal_direction: 'RISING',
    threshold_percent: 10,
    forecast_horizon_days: 7,
    predicted_outcome: 'UP',
    missing_data_policy: 'NO_SIGNAL',
    ...overrides,
  })
  assert.equal(result.ok, true)
  if (!result.ok) throw new Error(result.errors.join(' '))
  return result.value
}

test('Arena participant definitions are deterministic and versioned', () => {
  const first = arenaParticipants()
  const second = arenaParticipants()
  assert.deepEqual(second, first)
  assert.equal(first.participants.length, 4)
  assert.ok(first.participants.every((participant) => participant.deterministic && !participant.ai_agent))
  assert.ok(first.participants.every((participant) => participant.version === 'notch-agent-arena-participant/1'))
  assert.ok(first.participants.every((participant) => participant.participant_config_hash.startsWith('fnv1a32:')))
  assert.ok(first.participants[0].strategy_hash.startsWith('fnv1a32:'))
  assert.equal(first.participants[2].strategy_hash.startsWith('fnv1a32:'), true)
})

test('compatible saved strategies join once and incompatible strategies are disclosed', () => {
  const compatible = arenaParticipants(strategy())
  assert.equal(compatible.excluded.length, 0)
  assert.equal(compatible.participants.length, 5)
  assert.equal(compatible.participants.at(-1).kind, 'USER_STRATEGY')

  const incompatible = strategy({ topic: 'Bitcoin' })
  const set = arenaParticipants(incompatible)
  assert.equal(set.participants.length, 4)
  assert.equal(set.excluded.length, 1)
  assert.match(set.excluded[0].reason, /Nvidia/i)
  assert.deepEqual(isArenaCompatible(incompatible), { ok: false, reason: 'Arena V1 uses the frozen Nvidia Wikimedia dataset only.' })
})

test('match replay is deterministic, fairly aligned, and read-only', () => {
  const participants = builtInArenaParticipants()
  const first = runArenaMatch(NVIDIA_MOMENTUM_DATASET, participants)
  const second = runArenaMatch(NVIDIA_MOMENTUM_DATASET, participants)
  assert.deepEqual(second, first)
  assert.equal(first.schema_version, 'notch-agent-arena/1')
  assert.equal(first.execution.wallet_action, false)
  assert.equal(first.execution.ai_inference, false)
  assert.ok(first.shared_eligible_dates.length > 0)
  assert.ok(first.results.every((result) => result.eligible_windows === first.shared_eligible_dates.length))
  assert.ok(first.results.every((result) => result.decision_records.every((record) => record.signal_cutoff_utc.endsWith('23:59:59Z'))))
  const evidenceLedgerShapes = first.results.map((result) => first.shared_benchmark_signal_dates.map((date) => {
    const record = result.decision_records.find((item) => item.signal_date === date)
    return `${date}:${record?.signal_evidence_refs.join(',') ?? 'missing'}`
  }).join('|'))
  assert.equal(new Set(evidenceLedgerShapes).size, 1)
  assert.ok(first.leaderboard[0].rank === 1)
  assert.ok(first.results.every((result) => result.strategy_hash.startsWith('fnv1a32:')))
})

test('later target changes cannot alter signal or cutoff decisions', () => {
  const participants = builtInArenaParticipants()
  const first = runArenaMatch(NVIDIA_MOMENTUM_DATASET, participants)
  const changed = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date >= '2026-11-04' ? { ...row, views: 0 } : row),
  }
  const second = runArenaMatch(changed, participants)
  const firstMomentum = first.results[0].decision_records.map(({ signal_date, prediction, momentum_bps, threshold_bps }) => ({ signal_date, prediction, momentum_bps, threshold_bps }))
  const secondMomentum = second.results[0].decision_records.map(({ signal_date, prediction, momentum_bps, threshold_bps }) => ({ signal_date, prediction, momentum_bps, threshold_bps }))
  assert.deepEqual(secondMomentum, firstMomentum)
  assert.deepEqual(second.shared_candidate_dates, first.shared_candidate_dates)
  const settled = first.results[0].decision_records.find((record) => record.status === 'SETTLED')
  assert.ok(settled)
  assert.ok(settled.signal_evidence_refs.every((ref) => ref.split(':').at(-1) <= settled.signal_date))
  assert.ok(settled.outcome_evidence_refs.some((ref) => ref.split(':').at(-1) > settled.signal_date))
})

test('risk caps, accounting, and insufficient balance remain explicit', () => {
  const participant = builtInArenaParticipants()[0]
  const capped = runArenaMatch(NVIDIA_MOMENTUM_DATASET, [participant], {
    risk_policy: { ...ARENA_DEFAULT_RISK_POLICY, stake_fraction: 0.5 },
  })
  const cappedResult = capped.results[0]
  assert.ok(cappedResult.risk_limit_violations_prevented > 0)
  assert.ok(cappedResult.decision_records.filter((record) => record.status === 'SETTLED').every((record) => record.stake <= 250))
  const settledNet = cappedResult.decision_records.filter((record) => record.status === 'SETTLED').reduce((sum, record) => sum + (record.correct ? record.stake : -record.stake), 0)
  assert.equal(cappedResult.ending_credits, cappedResult.starting_credits + settledNet)

  const empty = runArenaMatch(NVIDIA_MOMENTUM_DATASET, [participant], {
    risk_policy: { ...ARENA_DEFAULT_RISK_POLICY, initial_credits: 0 },
  })
  assert.ok(empty.results[0].insufficient_balance_skips > 0)
  assert.equal(empty.results[0].ending_credits, 0)
  assert.ok(empty.results[0].decision_records.some((record) => record.reason === 'INSUFFICIENT_BALANCE'))
})

test('missing observations and zero baselines are unavailable, never imputed', () => {
  const participant = builtInArenaParticipants()[0]
  const missing = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date === '2026-10-21' ? { ...row, views: null } : row),
  }
  const missingMatch = runArenaMatch(missing, [participant])
  assert.ok(missingMatch.results[0].unavailable > 0)
  assert.ok(missingMatch.results[0].decision_records.some((record) => record.status === 'UNAVAILABLE'))

  const zero = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date <= '2026-10-07' ? { ...row, views: 0 } : row),
  }
  const zeroMatch = runArenaMatch(zero, [participant])
  assert.ok(zeroMatch.results[0].decision_records.some((record) => record.reason === 'ZERO_BASELINE'))
})

test('ranking and no-execution boundary are present in the inspectable source', () => {
  const source = readFileSync(new URL('../src/pages/Arena.tsx', import.meta.url), 'utf8')
  const engine = readFileSync(new URL('../src/arena/arena.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /NEAR_AI_KEY|ft_transfer_call|signAndSendTransaction|entryIntent/i)
  assert.doesNotMatch(engine, /NEAR_AI_KEY|fetch\(|signAndSendTransaction|entryIntent|near_ai/i)
  const match = runArenaMatch(NVIDIA_MOMENTUM_DATASET, builtInArenaParticipants())
  assert.deepEqual(match.leaderboard.map((row) => row.rank), [1, 2, 3, 4])
  assert.ok(match.overlapping_windows.disclosure.includes('not independent'))
})
