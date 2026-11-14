import test from 'node:test'
import assert from 'node:assert/strict'
import { historicalNotificationPreview, notificationTypeLabel } from '../src/notifications/notifications.ts'

test('historical notification preview is explicitly separated from wallet inbox state', () => {
  assert.equal(historicalNotificationPreview.type, 'MARKET_RESOLVED')
  assert.match(historicalNotificationPreview.title, /Historical fixture/)
  assert.match(historicalNotificationPreview.body, /not tied to your wallet/)
  assert.equal(historicalNotificationPreview.provenance.finality, 'historical fixture')
})

test('notification labels preserve the three truthful V1 types', () => {
  assert.equal(notificationTypeLabel('MARKET_RESOLVED'), 'MARKET RESOLVED')
  assert.equal(notificationTypeLabel('CLAIM_READY'), 'CLAIM READY')
  assert.equal(notificationTypeLabel('REFUND_READY'), 'REFUND READY')
})
