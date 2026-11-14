import { Bell, Check, ExternalLink, RefreshCw, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useNotifications } from '../notifications/NotificationsProvider'
import { formatNotificationDate, historicalNotificationPreview, notificationTypeLabel } from '../notifications/notifications'
import './Notifications.css'

function NotificationRow({ notification, onRead }: { notification: ReturnType<typeof useNotifications>['notifications'][number]; onRead: (id: string) => void }) {
  return (
    <article className={`notification-row${notification.unread ? ' is-unread' : ''}`}>
      <div className="notification-row-mark" aria-hidden="true"><Bell size={17} /></div>
      <div className="notification-row-main">
        <div className="notification-row-top">
          <span className={`notification-kind notification-kind-${notification.type.toLowerCase()}`}>{notificationTypeLabel(notification.type)}</span>
          {notification.unread && <span className="notification-unread">UNREAD</span>}
          <time dateTime={notification.created_at}>{formatNotificationDate(notification.created_at)}</time>
        </div>
        <h2>{notification.title}</h2>
        <p>{notification.body}</p>
        <div className="notification-row-bottom">
          <span className="notification-provenance">FINALIZED · {notification.provenance.market_block_hash ? 'block-provenance' : 'final read'}</span>
          <Link to={notification.href} onClick={() => { if (notification.unread) void onRead(notification.notification_id) }}>
            Open {notification.type === 'MARKET_RESOLVED' ? 'market' : 'Portfolio'} <ExternalLink size={13} aria-hidden="true" />
          </Link>
        </div>
      </div>
    </article>
  )
}

export function Notifications() {
  const { session, notifications, unreadCount, reconciliation, loading, error, refresh, markRead, markAllRead } = useNotifications()
  const [showPreview, setShowPreview] = useState(false)

  return (
    <>
      <header className="page-head notifications-head">
        <div>
          <p className="eyebrow">NOTIFICATION INBOX / V1</p>
          <h1>Know when the market moves.</h1>
          <p>Read-only wallet alerts appear after a finalized market read confirms a real position, resolution, claimable payout, or refundable balance.</p>
        </div>
        <div className="notification-proof-badge"><ShieldCheck size={18} aria-hidden="true" /><span>FINALIZED READS ONLY</span></div>
      </header>

      {!session ? (
        <section className="notification-auth-card">
          <div className="notification-auth-icon"><ShieldCheck size={22} aria-hidden="true" /></div>
          <div>
            <span className="creator-label">WALLET-SCOPED INBOX</span>
            <h2>Verify wallet ownership to load private notifications.</h2>
            <p>Notifications use the existing NEP-413 session. The API never trusts an account ID from the request and does not expose another wallet's inbox.</p>
          </div>
          <Link className="btn btn-accent" to="/app/vault">Verify in Vault</Link>
        </section>
      ) : (
        <>
          <section className="notification-toolbar" aria-label="Notification controls">
            <div><strong>{unreadCount}</strong> unread <span className="notification-toolbar-account">· {session.accountId}</span></div>
            <div className="notification-toolbar-actions">
              <button className="btn btn-quiet" type="button" onClick={() => { void refresh() }} disabled={loading}><RefreshCw size={15} aria-hidden="true" /> Refresh</button>
              <button className="btn btn-quiet" type="button" onClick={() => { void markAllRead() }} disabled={!unreadCount}>Mark all read</button>
            </div>
          </section>
          {error && <div className="creator-error creator-alert" role="alert">{error.message}</div>}
          {reconciliation && <p className="notification-reconcile-note">On-return reconciliation · finalized chain reads · last checked {formatNotificationDate(reconciliation.observed_at)}</p>}
          <section className="notification-list" aria-live="polite">
            {loading && <p className="creator-muted">Checking finalized market state…</p>}
            {!loading && notifications.length === 0 && <div className="notification-empty"><Check size={19} aria-hidden="true" /><strong>No verified alerts yet.</strong><p>Notch will add an alert only after this wallet's real position and the market's finalized state agree.</p></div>}
            {notifications.map((notification) => <NotificationRow key={notification.notification_id} notification={notification} onRead={markRead} />)}
          </section>
        </>
      )}

      <section className="notification-demo-card">
        <div>
          <span className="creator-label">JUDGE PREVIEW</span>
          <h2>See the inbox without inventing a live resolution.</h2>
          <p>This uses the verified historical Nvidia replay only. It is not stored, not wallet-scoped, and cannot trigger a claim.</p>
        </div>
        <button className="btn btn-quiet" type="button" onClick={() => setShowPreview((value) => !value)}>{showPreview ? 'Hide preview' : 'Show historical preview'}</button>
        {showPreview && <NotificationRow notification={historicalNotificationPreview} onRead={() => undefined} />}
      </section>
    </>
  )
}
