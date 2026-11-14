import type { Notification, NotificationType } from '../api/types'

export const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  MARKET_RESOLVED: 'MARKET RESOLVED',
  CLAIM_READY: 'CLAIM READY',
  REFUND_READY: 'REFUND READY',
}

export function notificationTypeLabel(type: NotificationType): string {
  return NOTIFICATION_TYPE_LABELS[type] ?? type
}

export function formatNotificationDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

/** Clearly separated UI-only preview using the verified historical Nvidia replay. */
export const historicalNotificationPreview: Notification = {
  notification_id: 'historical_fixture_nvidia_resolved',
  type: 'MARKET_RESOLVED',
  market_id: 's3b-short-trend-nvidia-20261112T040029Z',
  title: 'Historical fixture · prediction resolved',
  body: 'Verified historical Nvidia replay resolved UP. This preview is not tied to your wallet and is not a live alert.',
  href: '/app/markets/s3b-short-trend-nvidia-20261112T040029Z',
  created_at: '2026-11-12T04:00:29Z',
  read_at: null,
  unread: true,
  outcome: 'UP',
  prediction_status: 'CORRECT',
  amount: null,
  provenance: {
    finality: 'historical fixture',
    observed_at: '2026-11-12T04:00:29Z',
    market_block_height: null,
    market_block_hash: null,
    position_block_height: null,
    position_block_hash: null,
  },
}
