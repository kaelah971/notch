import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { NVIDIA_MOMENTUM_DATASET } from '../src/practice/fixtures/nvidia-momentum-v1.ts'
import { addPracticePosition, emptyPracticeState, getPracticeLedger } from '../src/practice/practice.ts'
import {
  AUTOPILOT_DEFAULT_RISK,
  approveManualReview,
  assessMarketCompatibility,
  createPolicy,
  emptyAutopilotState,
  evaluateAutopilot,
  normalizeAutopilotState,
  readAutopilotState,
  setPolicyStatus,
  strategyAutopilotCompatibility,
  writeAutopilotState,
} from '../src/autopilot/autopilot.ts'
import { createStrategyFromDraft, emptyStrategyDraft } from '../src/strategy/strategy.ts'
import { builtInArenaParticipants, runArenaMatch } from '../src/arena/arena.ts'

const NOW = '2026-11-10T12:00:00.000Z'
const RULE_HASH = 'sha256:' + 'a'.repeat(64)

function strategy(overrides = {}) {
  const result = createStrategyFromDraft({
    ...emptyStrategyDraft(),
    name: 'Nvidia paper policy',
    source_id: 'wikimedia-pageviews-v1',
    topic: 'Nvidia',
    lookback_days: 7,
    signal_direction: 'FALLING',
    threshold_percent: 5,
    forecast_horizon_days: 7,
    predicted_outcome: 'DOWN',
    missing_data_policy: 'NO_SIGNAL',
    ...overrides,
  })
  assert.equal(result.ok, true)
  if (!result.ok) throw new Error(result.errors.join(' '))
  return result.value
}

function market(overrides = {}) {
  return {
    market_id: 'published-nvidia-paper-test',
    mode: 'trend_trading',
    question: 'FORECAST (not a replay): Nvidia attention next window',
    choices: ['UP', 'DOWN'],
    source_id: 'wikimedia-pageviews-v1',
    rule_hash: RULE_HASH,
    status: 'open',
    display_status: 'open_future',
    is_historical_replay: false,
    is_future_prediction: true,
    entries_open: true,
    entries_paused: false,
    open_at_utc: '2026-11-01T00:00:00.000Z',
    close_at_utc: '2026-11-11T00:00:00.000Z',
    resolve_after_utc: '2026-11-18T00:00:00.000Z',
    totals: ['0', '0'],
    escrow_total: '0',
    paid_total: '0',
    winning_outcome: null,
    winning_choice: null,
    evidence_hash: null,
    resolution_kind: null,
    created_at_utc: '2026-11-01T00:00:00.000Z',
    resolved_at_utc: null,
    battle: null,
    rule_available: true,
    evidence_available: false,
    rule: {
      rule_hash: RULE_HASH,
      mode: 'trend_trading',
      source: {
        id: 'wikimedia-pageviews-v1',
        provider: 'Wikimedia Analytics API',
        project: 'en.wikipedia.org',
        access: 'all-access',
        agent: 'user',
        metric: 'daily_pageviews',
        article: 'Nvidia',
      },
      topics: [{ topic_id: 'nvidia', article_title: 'Nvidia' }],
      strategy_window: { lookback_days: 7, horizon_days: 7 },
      formula: { version: 'growth-threshold-v1', up_if: 'growth_bps >= threshold_bps', down_if: 'growth_bps < threshold_bps' },
      observation: { replay: false },
    },
    ...overrides,
  }
}

function activeState(rule = strategy(), risk = AUTOPILOT_DEFAULT_RISK, mode = 'PAPER_AUTO') {
  const policy = createPolicy(rule, risk, mode, NOW)
  return { ...emptyAutopilotState(), policy }
}

test('market compatibility requires published source, topic, window, deadline and resolution semantics', () => {
  const rule = strategy()
  const eligible = assessMarketCompatibility(rule, market(), NOW)
  assert.equal(eligible.eligible, true)

  const bitcoin = assessMarketCompatibility(rule, market({ rule: { ...market().rule, topics: [{ article_title: 'Bitcoin' }] } }), NOW)
  assert.equal(bitcoin.eligible, false)
  assert.ok(bitcoin.reasons.some((reason) => reason.code === 'TOPIC_MISMATCH'))

  const replay = assessMarketCompatibility(rule, market({ is_historical_replay: true, display_status: 'historical_replay_open', rule: { ...market().rule, observation: { replay: true } } }), NOW)
  assert.ok(replay.reasons.some((reason) => reason.code === 'HISTORICAL_REPLAY'))

  const closed = assessMarketCompatibility(rule, market({ close_at_utc: '2026-11-10T11:00:00.000Z' }), NOW)
  assert.ok(closed.reasons.some((reason) => reason.code === 'DEADLINE_PASSED'))
})

test('paper-auto approves once, records provenance and deduplicates repeated evaluation', () => {
  const rule = strategy()
  const state = activeState(rule)
  const first = evaluateAutopilot(state, rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  assert.equal(first.actions[0].status, 'PAPER_ENTRY_APPROVED')
  assert.equal(first.actions[0].paper_result, 'PAPER_EXECUTED')
  assert.equal(first.actions[0].recommendation.direction, 'DOWN')
  assert.equal(first.actions[0].recommendation.eligibility_status, 'ELIGIBLE')
  assert.equal(first.actions[0].recommendation.freshness_status, 'FRESH')
  assert.match(first.actions[0].audit_id, /^paper_audit_/)
  assert.equal(first.actions[0].stake, 100)
  assert.match(first.actions[0].simulated_position_id, /^paper_position_/)
  assert.equal(first.actions[0].evidence_digest, first.strategy_evaluation.result_digest)
  assert.equal(first.actions[0].market_rule_hash, RULE_HASH)
  assert.equal(first.ledger.current_exposure, 100)
  assert.equal(first.actions[0].run_mode, 'FORWARD_EVALUATION')

  const second = evaluateAutopilot(first.state, rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: '2026-11-10T12:01:00.000Z' })
  assert.equal(second.actions[0].status, 'ALREADY_PROCESSED')
  assert.equal(second.state.actions.filter((action) => action.status === 'PAPER_ENTRY_APPROVED').length, 1)
  assert.equal(second.ledger.current_exposure, 100)
})

test('manual review creates no position until approval and approval is idempotent', () => {
  const rule = strategy()
  const first = evaluateAutopilot(activeState(rule, AUTOPILOT_DEFAULT_RISK, 'MANUAL_REVIEW'), rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  assert.equal(first.actions[0].status, 'NEEDS_MANUAL_REVIEW')
  assert.equal(first.actions[0].paper_result, 'NO_ACTION')
  assert.equal(first.actions[0].simulated_position_id, null)
  assert.equal(first.ledger.current_exposure, 0)

  const approved = approveManualReview(first.state, first.actions[0].action_id, '2026-11-10T12:02:00.000Z')
  assert.equal(approved.action?.status, 'PAPER_ENTRY_APPROVED')
  assert.equal(approved.state.actions.filter((action) => action.status === 'PAPER_ENTRY_APPROVED').length, 1)
  assert.equal(approveManualReview(approved.state, first.actions[0].action_id, '2026-11-10T12:03:00.000Z').action, null)
})

test('risk engine enforces positions, exposure, cooldown and daily loss limits', () => {
  const rule = strategy()
  const secondMarket = market({ market_id: 'published-nvidia-paper-test-2' })
  const positionLimited = evaluateAutopilot(activeState(rule, { ...AUTOPILOT_DEFAULT_RISK, max_positions: 1, cooldown_seconds: 0 }, 'PAPER_AUTO'), rule, NVIDIA_MOMENTUM_DATASET, [market(), secondMarket], { now: NOW })
  assert.equal(positionLimited.actions[0].status, 'PAPER_ENTRY_APPROVED')
  assert.equal(positionLimited.actions[1].status, 'BLOCKED_BY_RISK')
  assert.equal(positionLimited.actions[1].reason_code, 'MAX_POSITIONS')

  const exposureLimited = evaluateAutopilot(activeState(rule, { ...AUTOPILOT_DEFAULT_RISK, max_exposure_credits: 50 }, 'PAPER_AUTO'), rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  assert.equal(exposureLimited.actions[0].reason_code, 'MAX_EXPOSURE')

  const cooldown = evaluateAutopilot(activeState(rule, { ...AUTOPILOT_DEFAULT_RISK, max_positions: 2, max_exposure_credits: 500, cooldown_seconds: 3600 }, 'PAPER_AUTO'), rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  const laterMarket = market({ market_id: 'published-nvidia-paper-test-3' })
  const cooldownLater = evaluateAutopilot(cooldown.state, rule, NVIDIA_MOMENTUM_DATASET, [laterMarket], { now: '2026-11-10T12:01:00.000Z' })
  assert.equal(cooldownLater.actions[0].status, 'COOLDOWN')

  const lossState = evaluateAutopilot(activeState(rule, { ...AUTOPILOT_DEFAULT_RISK, max_positions: 2, max_exposure_credits: 500, cooldown_seconds: 0, daily_loss_limit_credits: 100 }, 'PAPER_AUTO'), rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  const lossAction = { ...lossState.actions[0], settled_result: 'LOSS', settled_at_utc: NOW }
  const lossBlocked = evaluateAutopilot({ ...lossState.state, actions: [lossAction] }, rule, NVIDIA_MOMENTUM_DATASET, [laterMarket], { now: '2026-11-10T12:05:00.000Z' })
  assert.equal(lossBlocked.actions[0].reason_code, 'DAILY_LOSS_LIMIT')
})

test('paused and stopped policies refuse new paper actions', () => {
  const rule = strategy()
  const paused = evaluateAutopilot(setPolicyStatus(activeState(rule), 'PAUSED', NOW), rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  assert.equal(paused.actions[0].status, 'PAUSED')
  assert.equal(paused.actions[0].paper_result, 'BLOCKED')
  assert.equal(paused.actions[0].reason_code, 'POLICY_PAUSED')
  const stopped = evaluateAutopilot(setPolicyStatus(activeState(rule), 'STOPPED', NOW), rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  assert.equal(stopped.actions[0].reason_code, 'POLICY_STOPPED')
})

test('no market and stale evidence remain honest and never fabricate eligibility', () => {
  const rule = strategy()
  const empty = evaluateAutopilot(activeState(rule), rule, NVIDIA_MOMENTUM_DATASET, [], { now: NOW })
  assert.equal(empty.eligible_market_count, 0)
  assert.equal(empty.actions[0].status, 'MARKET_INELIGIBLE')
  assert.equal(empty.actions[0].paper_result, 'BLOCKED')
  assert.equal(empty.actions[0].recommendation.eligibility_status, 'BLOCKED')
  assert.equal(empty.actions[0].reason_code, 'NO_MARKETS_RETURNED')
  const repeated = evaluateAutopilot(empty.state, rule, NVIDIA_MOMENTUM_DATASET, [], { now: '2026-11-10T12:01:00.000Z' })
  assert.equal(repeated.actions[0].status, 'ALREADY_PROCESSED')
  assert.equal(repeated.actions[0].paper_result, 'NO_ACTION')

  const stale = evaluateAutopilot(activeState(rule), rule, NVIDIA_MOMENTUM_DATASET, [market({ close_at_utc: '2026-11-20T00:00:00.000Z' })], { now: '2026-11-14T12:00:00.000Z' })
  assert.equal(stale.actions[0].status, 'INSUFFICIENT_EVIDENCE')
  assert.equal(stale.actions[0].paper_result, 'BLOCKED')
  assert.equal(stale.actions[0].recommendation.freshness_status, 'STALE')
  assert.equal(stale.actions[0].reason_code, 'STALE_EVIDENCE')
})

test('target-window changes do not alter the paper signal or cutoff', () => {
  const rule = strategy()
  const changed = {
    ...NVIDIA_MOMENTUM_DATASET,
    observations: NVIDIA_MOMENTUM_DATASET.observations.map((row) => row.date >= '2026-11-04' ? { ...row, views: 0 } : row),
  }
  const first = evaluateAutopilot(activeState(rule), rule, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW, run_mode: 'HISTORICAL_SIMULATION' })
  const second = evaluateAutopilot(activeState(rule), rule, changed, [market()], { now: NOW, run_mode: 'HISTORICAL_SIMULATION' })
  assert.equal(second.actions[0].strategy_prediction, first.actions[0].strategy_prediction)
  assert.equal(second.actions[0].decision_cutoff_utc, first.actions[0].decision_cutoff_utc)
  assert.equal(second.actions[0].signal_momentum_bps, first.actions[0].signal_momentum_bps)
  assert.equal(second.actions[0].recommendation.freshness_status, 'FROZEN_HISTORICAL')
})

test('Arena participant handoff produces a deterministic paper recommendation and persisted audit', () => {
  const participants = builtInArenaParticipants()
  const participant = participants[0]
  const match = runArenaMatch(NVIDIA_MOMENTUM_DATASET, participants)
  assert.equal(match.execution.ai_inference, false)
  assert.equal(match.participant_configs.length, 4)
  const policy = createPolicy(
    participant.strategy,
    { ...AUTOPILOT_DEFAULT_RISK, cooldown_seconds: 0 },
    'PAPER_AUTO',
    NOW,
    null,
    { agent_id: participant.participant_id, agent_name: participant.name, agent_kind: participant.kind, agent_behavior: participant.behavior },
  )
  const result = evaluateAutopilot({ ...emptyAutopilotState(), policy }, participant.strategy, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW, run_mode: 'HISTORICAL_SIMULATION' })
  const action = result.actions[0]
  assert.equal(action.paper_result, 'PAPER_EXECUTED')
  assert.equal(action.recommendation.agent_id, participant.participant_id)
  assert.equal(action.recommendation.agent_name, participant.name)
  assert.equal(action.recommendation.freshness_status, 'FROZEN_HISTORICAL')
  assert.match(action.recommendation.evidence_snapshot_id, /^wikimedia_snapshot_/)
  assert.equal(action.recommendation.decision_timestamp_utc, action.decision_cutoff_utc)
  const memory = { value: null, getItem() { return this.value }, setItem(_key, value) { this.value = value } }
  assert.equal(writeAutopilotState(result.state, memory), true)
  const readback = readAutopilotState(memory)
  assert.equal(readback.actions[0].audit_id, action.audit_id)
  assert.equal(readback.actions[0].recommendation.evidence_digest, action.recommendation.evidence_digest)
  assert.match(match.result_digest, /^fnv1a32:/)
})

test('strategy revisions change policy hashes and practice accounting matches reserved paper exposure', () => {
  const original = strategy()
  const revised = strategy({ threshold_percent: 10 })
  const firstPolicy = createPolicy(original, AUTOPILOT_DEFAULT_RISK, 'PAPER_AUTO', NOW)
  const secondPolicy = createPolicy(revised, AUTOPILOT_DEFAULT_RISK, 'PAPER_AUTO', '2026-11-10T12:10:00.000Z', firstPolicy)
  assert.notEqual(firstPolicy.strategy_hash, secondPolicy.strategy_hash)
  assert.equal(secondPolicy.version, firstPolicy.version + 1)

  const practice = addPracticePosition(emptyPracticeState(), market(), 0, 100, [market()], Date.parse(NOW))
  assert.equal(practice.validation.ok, true)
  const ledger = getPracticeLedger(practice.state, [market()])
  const paper = evaluateAutopilot(activeState(original), original, NVIDIA_MOMENTUM_DATASET, [market()], { now: NOW })
  assert.equal(paper.ledger.current_exposure, ledger.reserved_credits)
  assert.equal(paper.ledger.available_budget, ledger.available_credits)
})

test('local persistence strips malformed rows and the feature has no signing or inference path', () => {
  const normalized = normalizeAutopilotState({ version: 1, policy: null, actions: [{ nope: true }] })
  assert.deepEqual(normalized.actions, [])
  const memory = { value: null, getItem() { return this.value }, setItem(_key, value) { this.value = value } }
  const state = activeState(strategy())
  assert.equal(writeAutopilotState(state, memory), true)
  assert.deepEqual(readAutopilotState(memory), state)
  const source = readFileSync(new URL('../src/autopilot/autopilot.ts', import.meta.url), 'utf8')
  const page = readFileSync(new URL('../src/pages/Autopilot.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /NEAR_AI_KEY|fetch\(|entryIntent|signAndSendTransaction|ft_transfer_call|private.?key/i)
  assert.doesNotMatch(page, /entryIntent|signAndSendTransaction|ft_transfer_call|NEAR_AI_KEY/i)
})

test('unsupported saved topic cannot be activated as a supported evidence policy', () => {
  const bitcoin = strategy({ topic: 'Bitcoin' })
  const compatibility = strategyAutopilotCompatibility(bitcoin, NVIDIA_MOMENTUM_DATASET)
  assert.equal(compatibility.ok, false)
  assert.match(compatibility.reason, /EVALUATED|genuine|fixture|supported/i)
})
