import assert from 'node:assert/strict'
import test from 'node:test'
import { summarizeForecast } from '../src/api/predictions.ts'
import { callCardBadge, callCardOutcomeSuffix } from '../src/share/card.ts'

const call = (status, outcome = null) => ({
  kind: 'call',
  title: 'Test market',
  choice: 'UP',
  stake: '1',
  confirmedAt: null,
  txRef: null,
  verification: 'contract-read',
  result: { status, outcome },
  account: null,
  url: 'https://notch.example/app/markets/test',
})

test('forecast passport counts market-level result statuses and leaves zero accuracy unavailable', () => {
  assert.deepEqual(summarizeForecast([
    { prediction_status: 'CORRECT' },
    { prediction_status: 'INCORRECT' },
    { prediction_status: 'PENDING' },
    { prediction_status: 'VOIDED' },
    { prediction_status: 'UNKNOWN' },
  ]), {
    total: 5,
    correct: 1,
    incorrect: 1,
    pending: 1,
    voided: 1,
    unknown: 1,
    completed: 2,
    accuracy: 50,
  })
  assert.equal(summarizeForecast([]).accuracy, null)
})

test('resolution-aware call cards expose the result without changing open-call language', () => {
  assert.equal(callCardBadge(call('CORRECT', 'UP')), '✓ Prediction correct')
  assert.equal(callCardOutcomeSuffix(call('CORRECT', 'UP')), ' · final UP')
  assert.equal(callCardBadge(call('INCORRECT', 'DOWN')), '✕ Prediction incorrect')
  assert.equal(callCardOutcomeSuffix(call('INCORRECT', 'DOWN')), ' · final DOWN')
  assert.equal(callCardBadge(call('VOIDED')), '↺ Prediction voided')
  assert.equal(callCardOutcomeSuffix(call('VOIDED')), ' · refunded')
  assert.equal(callCardBadge(call('UNKNOWN')), '? Result unavailable')
  assert.equal(callCardBadge({ ...call('PENDING'), result: undefined }), '✓ Position verified onchain')
  assert.equal(callCardOutcomeSuffix(call('PENDING')), '')
})
