import assert from 'node:assert/strict'
import test from 'node:test'
import { callCardBadge } from '../src/share/card.ts'
import {
  addPracticePosition,
  classifyPracticePosition,
  emptyPracticeState,
  getPracticeLedger,
  readPracticeState,
  summarizePractice,
  validatePracticeEntry,
  writePracticeState,
} from '../src/practice/practice.ts'

// Explicit test/demo fixture only; it never represents real participant activity.
const market = (overrides = {}) => ({
  market_id: 'practice-market',
  mode: 'trend_trading',
  question: 'Will the practice topic grow?',
  choices: ['UP', 'DOWN'],
  source_id: 'wikimedia-pageviews',
  rule_hash: 'sha256:test',
  status: 'open',
  display_status: 'open_future',
  is_historical_replay: false,
  is_future_prediction: true,
  entries_open: true,
  entries_paused: false,
  open_at_utc: '2026-01-01T00:00:00.000Z',
  close_at_utc: '2030-01-01T00:00:00.000Z',
  resolve_after_utc: '2030-01-02T00:00:00.000Z',
  totals: ['0', '0'],
  escrow_total: '0',
  paid_total: '0',
  winning_outcome: null,
  winning_choice: null,
  evidence_hash: null,
  resolution_kind: null,
  created_at_utc: '2026-01-01T00:00:00.000Z',
  resolved_at_utc: null,
  battle: null,
  rule_available: true,
  evidence_available: false,
  ...overrides,
})

const position = (choiceIndex = 0) => ({ choice_index: choiceIndex })

class MemoryStorage {
  values = new Map()
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, value) }
}

test('practice classification uses only finalized status, resolution kind, winner, and evidence', () => {
  assert.equal(classifyPracticePosition(position(), market()), 'PENDING')
  assert.equal(classifyPracticePosition(position(), market({ status: 'resolved', display_status: 'resolved', winning_outcome: 0, winning_choice: 'UP', resolution_kind: 'winning_outcome', evidence_available: true })), 'CORRECT')
  assert.equal(classifyPracticePosition(position(), market({ status: 'resolved', display_status: 'resolved', winning_outcome: 1, winning_choice: 'DOWN', resolution_kind: 'winning_outcome', evidence_available: true })), 'INCORRECT')
  assert.equal(classifyPracticePosition(position(), market({ status: 'voided', display_status: 'voided', resolution_kind: 'tie' })), 'VOIDED')
  assert.equal(classifyPracticePosition(position(), market({ status: 'resolved', display_status: 'resolved', winning_outcome: 0, resolution_kind: 'winning_outcome', evidence_available: false })), 'UNKNOWN')
  assert.equal(classifyPracticePosition(position(), null), 'UNKNOWN')
})

test('practice budget validates stake, deadline, duplicate calls, and persistence', () => {
  const now = Date.parse('2027-01-01T00:00:00.000Z')
  const first = market()
  const state = emptyPracticeState()
  const added = addPracticePosition(state, first, 0, 250, [first], now)
  assert.equal(added.validation.ok, true)
  assert.equal(added.state.positions.length, 1)
  assert.equal(getPracticeLedger(added.state, [first]).available_credits, 750)
  const resolved = market({ status: 'resolved', display_status: 'resolved', winning_outcome: 0, winning_choice: 'UP', resolution_kind: 'winning_outcome', evidence_available: true })
  assert.equal(getPracticeLedger(added.state, [resolved]).available_credits, 1_250)
  assert.equal(validatePracticeEntry(first, added.state, 1, 1, getPracticeLedger(added.state, [first]), now).code, 'DUPLICATE_MARKET')
  const second = market({ market_id: 'second-market' })
  assert.equal(validatePracticeEntry(second, added.state, 0, 751, getPracticeLedger(added.state, [first, second]), now).code, 'INSUFFICIENT_CREDITS')
  const closed = market({ market_id: 'closed-market', status: 'closed', display_status: 'closed', entries_open: false })
  assert.equal(validatePracticeEntry(closed, added.state, 0, 1, getPracticeLedger(added.state, [first, closed]), now).code, 'MARKET_CLOSED')
  const expired = market({ market_id: 'expired-market', close_at_utc: '2026-12-31T00:00:00.000Z' })
  assert.equal(validatePracticeEntry(expired, added.state, 0, 1, getPracticeLedger(added.state, [first, expired]), now).code, 'MARKET_CLOSED')

  const storage = new MemoryStorage()
  assert.equal(writePracticeState(added.state, storage), true)
  assert.deepEqual(readPracticeState(storage), added.state)
})

test('practice share cards are labelled local practice instead of onchain verification', () => {
  assert.equal(callCardBadge({ kind: 'call', title: 'Practice', choice: 'UP', stake: '100', confirmedAt: null, txRef: null, verification: 'practice-local', result: { status: 'PENDING', outcome: null }, account: null, url: '' }), 'Practice · pending')
  assert.equal(callCardBadge({ kind: 'call', title: 'Practice', choice: 'UP', stake: '100', confirmedAt: null, txRef: null, verification: 'practice-local', result: { status: 'CORRECT', outcome: 'UP' }, account: null, url: '' }), 'Practice · correct')
})

test('practice summary reports sample-aware accuracy and correct streaks', () => {
  const rows = [
    { status: 'CORRECT', created_at_utc: '2026-01-01T00:00:00.000Z' },
    { status: 'CORRECT', created_at_utc: '2026-01-02T00:00:00.000Z' },
    { status: 'INCORRECT', created_at_utc: '2026-01-03T00:00:00.000Z' },
    { status: 'PENDING', created_at_utc: '2026-01-04T00:00:00.000Z' },
    { status: 'VOIDED', created_at_utc: '2026-01-05T00:00:00.000Z' },
    { status: 'UNKNOWN', created_at_utc: '2026-01-06T00:00:00.000Z' },
  ]
  assert.deepEqual(summarizePractice(rows), {
    total: 6, correct: 2, incorrect: 1, pending: 1, voided: 1, unknown: 1,
    completed: 3, accuracy: 66.66666666666666, current_streak: 0, best_streak: 2,
  })
})
