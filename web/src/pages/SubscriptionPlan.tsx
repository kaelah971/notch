import { useEffect, useState } from 'react'
import { ArrowUpRight, CalendarClock, Check, LockKeyhole, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { CreatorPaymentIntent, CreatorSubscriptions } from '../api/types'
import { useApi } from '../api/useApi'
import { clearCreatorSession, readCreatorSession, verifyCreatorOwnership, type StoredCreatorSession } from '../creator/session'
import { useWallet } from '../wallet/WalletProvider'
import { ErrorState, SkeletonList } from '../components/States'
import './CreatorStudio.css'

const emptySubscriptions: CreatorSubscriptions = { subscriber_subscriptions: [], creator_subscriptions: [] }

function formatBaseUnits(value: string, decimals: number) {
  const padded = value.padStart(decimals + 1, '0')
  const split = padded.length - decimals
  const fraction = padded.slice(split).replace(/0+$/, '')
  return fraction ? `${padded.slice(0, split)}.${fraction}` : padded.slice(0, split)
}

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
}

function dateText(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—'
}

export function SubscriptionPlan() {
  const { id } = useParams()
  const { accountId, connect, signMessage, signAndSend } = useWallet()
  const [state, reload] = useApi(() => api.subscriptionPlan(id ?? ''), [id])
  const [session, setSession] = useState<StoredCreatorSession | null>(() => readCreatorSession())
  const [intent, setIntent] = useState<CreatorPaymentIntent | null>(null)
  const [txHash, setTxHash] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [subState, refreshSubscriptions] = useApi(() => session ? api.subscriptions(session.token) : Promise.resolve({ data: emptySubscriptions }), [session?.token])

  useEffect(() => {
    if (session && accountId && session.accountId !== accountId) {
      clearCreatorSession()
      setSession(null)
      setIntent(null)
    }
  }, [accountId, session])

  if (state.status === 'loading') return <SkeletonList n={3} h={120} />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={reload} />
  const plan = state.data.data
  const subscription = subState.status === 'ok' ? subState.data.data.subscriber_subscriptions.find((item) => item.plan_id === plan.plan_id) : null
  const price = formatBaseUnits(plan.price_base_units, plan.token_decimals)

  async function verifyWallet() {
    if (!accountId) { connect(); setMessage('Connect a NEAR Testnet wallet before signing the ownership challenge.'); return }
    setBusy(true); setError(null); setMessage(null)
    try {
      const next = await verifyCreatorOwnership(accountId, signMessage)
      setSession(next)
      setMessage(`Wallet ownership verified for ${next.accountId}.`)
    } catch (reason) { setError(errorText(reason)) } finally { setBusy(false) }
  }

  async function verifyTransaction(hash: string, currentIntent = intent) {
    if (!session || !currentIntent || !hash.trim()) return
    setBusy(true); setError(null); setMessage('Checking finalized NEAR Testnet receipt evidence…')
    try {
      const result = await api.creatorVerifyPayment(session.token, currentIntent.intent_id, hash.trim())
      setIntent(result.data)
      setTxHash(hash.trim())
      if (result.data.status === 'VERIFIED') {
        await refreshSubscriptions()
        setMessage('Payment independently verified. Your subscription is active for the exact plan term.')
      } else if (result.data.status === 'PENDING') {
        setMessage('The transaction is not finalized yet. Retry verification after finality.')
      } else {
        setError(result.data.failure_message ?? 'The payment evidence was rejected. No subscription access was granted.')
      }
    } catch (reason) { setError(errorText(reason)) } finally { setBusy(false) }
  }

  async function purchaseOrRenew() {
    if (!session) { await verifyWallet(); return }
    setBusy(true); setError(null); setMessage(null)
    try {
      const created = (await api.subscriptionCreatePaymentIntent(session.token, plan.plan_id)).data
      setIntent(created)
      if (created.status === 'VERIFIED') { await refreshSubscriptions(); return }
      const confirmed = window.confirm(`Approve ${formatBaseUnits(created.amount_base_units, created.token_decimals)} ${created.token_symbol} on NEAR Testnet for ${plan.title}?\n\nDuration: ${plan.duration_days} days\nToken contract: ${created.token_contract}\nRecipient: ${created.recipient_account}\nMemo: ${created.memo}\n\nThis is a manual, non-recurring payment. Notch cannot sign or broadcast for you.`)
      if (!confirmed) { setMessage('Payment cancelled. No wallet transaction was requested.'); return }
      const result = await signAndSend({ receiverId: created.action.receiver_id, calls: [{ methodName: created.action.method_name, args: created.action.args, gasTgas: created.action.gas_tgas, depositYocto: created.action.attached_deposit_yocto }] })
      if (!result.hash) {
        setMessage('The wallet returned without an in-page hash. Paste the finalized Testnet transaction hash below.')
        return
      }
      await verifyTransaction(result.hash, created)
    } catch (reason) { setError(errorText(reason)) } finally { setBusy(false) }
  }

  async function cancel() {
    if (!session || !subscription) return
    setBusy(true); setError(null)
    try {
      await api.subscriptionCancel(session.token, subscription.subscription_id)
      await refreshSubscriptions()
      setMessage('Future renewal is cancelled. Already-paid access remains available until expiry.')
    } catch (reason) { setError(errorText(reason)) } finally { setBusy(false) }
  }

  const pending = intent && intent.status !== 'VERIFIED'
  return <div className="creator-detail subscription-detail">
    <header className="page-head creator-head">
      <div>
        <p className="eyebrow">RESEARCH SUBSCRIPTION / TESTNET</p>
        <h1>{plan.title}</h1>
        <p className="creator-detail-lede">{plan.description}</p>
        <div className="creator-detail-meta"><span>{plan.duration_days} days</span><span>{price} {plan.token_symbol}</span><span>{plan.subscriber_count} verified subscriber{plan.subscriber_count === 1 ? '' : 's'}</span><span>terms v{plan.terms_version}</span></div>
      </div>
      <div className="creator-proof-badge"><ShieldCheck size={18} aria-hidden="true" /><span>Manual Testnet payment · no recurring billing</span></div>
    </header>

    <div className="subscription-layout">
      <section className="creator-detail-card">
        <div className="creator-section-head"><div><span className="creator-label">PLAN COVERAGE</span><h2>Subscriber-only research</h2></div><LockKeyhole size={18} aria-hidden="true" /></div>
        <p className="creator-muted">The plan covers only the published premium revisions listed here. Access is checked by the server against your authenticated account and the active UTC term.</p>
        <div className="subscription-scope-list">{plan.scope.map((note) => <Link className="subscription-scope-row" to={`/app/research/notes/${encodeURIComponent(note.note_id)}`} key={note.note_id}><span><strong>{note.title ?? note.note_id}</strong><small>revision {note.revision ?? '—'} · {note.note_id}</small></span><ArrowUpRight size={15} aria-hidden="true" /></Link>)}</div>
      </section>

      <aside className="creator-detail-card subscription-side-card">
        <div className="creator-section-head"><div><span className="creator-label">YOUR ACCESS</span><h2>{subscription?.status ?? 'Not subscribed'}</h2></div><CalendarClock size={18} aria-hidden="true" /></div>
        {subscription?.access_active ? <><div className="subscription-expiry"><span>Access through</span><strong>{dateText(subscription.expires_at)}</strong></div><p className="creator-muted">Cancellation only disables future renewal. Your paid term remains valid.</p></> : <p className="creator-muted">Purchase this exact versioned plan to unlock its subscriber-only research. Payments are Testnet-only and manually approved in your wallet.</p>}
        {!session && <button className="btn btn-accent" type="button" onClick={verifyWallet} disabled={busy}>{busy ? 'Waiting for wallet…' : accountId ? 'Verify wallet to subscribe' : 'Connect wallet to subscribe'}</button>}
        {session && (!subscription || subscription.renewal_available) && <button className="btn btn-accent" type="button" onClick={purchaseOrRenew} disabled={busy}>{busy ? 'Preparing wallet approval…' : subscription?.access_active ? 'Renew manually' : 'Subscribe manually'}</button>}
        {session && subscription?.access_active && !subscription.renewal_cancelled && <button className="btn btn-quiet" type="button" onClick={cancel} disabled={busy}><XCircle size={14} aria-hidden="true" /> Cancel future renewal</button>}
        {subscription?.status === 'PAYMENT_PENDING' && <p className="creator-hint">Payment is pending finality. Use the verification panel below.</p>}
      </aside>
    </div>

    {pending && <section className="creator-premium-card subscription-payment-card"><div className="creator-premium-head"><div><span className="creator-label">PAYMENT STATUS</span><h2>{intent.status}</h2></div><RefreshCw size={20} aria-hidden="true" /></div><div className="creator-payment-grid"><span>Plan<strong>{plan.title}</strong></span><span>Amount<strong>{price} {intent.token_symbol}</strong></span><span>Token<strong>{intent.token_contract}</strong></span><span>Recipient<strong>{intent.recipient_account}</strong></span><span>Term<strong>{plan.duration_days} days</strong></span></div><label className="subscription-hash-label">Finalized Testnet transaction hash<input className="creator-payment-input" value={txHash} onChange={(event) => setTxHash(event.target.value)} placeholder="Paste the wallet transaction hash" /></label><div className="creator-actions"><button className="btn btn-accent" type="button" onClick={() => verifyTransaction(txHash)} disabled={busy || !txHash.trim() || intent.status === 'FAILED' || intent.status === 'EXPIRED'}>{busy ? 'Verifying…' : 'Retry verification'}</button>{(intent.status === 'FAILED' || intent.status === 'EXPIRED') && <button className="btn btn-quiet" type="button" onClick={() => { setIntent(null); setTxHash(''); setError(null) }}>Start a fresh payment</button>}</div></section>}
    {message && <div className="creator-notice" role="status"><Check size={15} aria-hidden="true" />{message}</div>}
    {error && <div className="creator-error" role="alert">{error}</div>}
  </div>
}
