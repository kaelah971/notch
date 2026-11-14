import { useEffect, useState } from 'react'
import { ArrowUpRight, CalendarClock, ExternalLink, FileText, LockKeyhole, ShieldCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { CreatorPremiumContent, CreatorPaymentIntent, CreatorResearchNote, CreatorSubscriptionPlan } from '../api/types'
import { useApi } from '../api/useApi'
import { clearCreatorSession, readCreatorSession, verifyCreatorOwnership, type StoredCreatorSession } from '../creator/session'
import { useWallet } from '../wallet/WalletProvider'
import { ErrorState, SkeletonList } from '../components/States'
import './CreatorStudio.css'

function formatBaseUnits(value: string | null, decimals: number | null) {
  if (!value || decimals == null) return '—'
  const padded = value.padStart(decimals + 1, '0')
  const split = padded.length - decimals
  const fraction = padded.slice(split).replace(/0+$/, '')
  return fraction ? `${padded.slice(0, split)}.${fraction}` : padded.slice(0, split)
}

function NoteCard({ note }: { note: CreatorResearchNote }) {
  return <Link className="creator-public-card" to={`/app/research/notes/${encodeURIComponent(note.note_id)}`}>
    <div className="creator-note-row-top"><span className="creator-label">{note.reference.label}</span><span className="creator-status creator-status-published">PUBLISHED</span></div>
    <h3>{note.title}</h3>
    <p>{note.thesis}</p>
    {note.premium.enabled && <span className="creator-premium-chip"><LockKeyhole size={12} aria-hidden="true" /> Premium Testnet unlock</span>}
    <div className="creator-public-card-meta"><span>{note.creator_account} · rev {note.revision}</span><span>Inspect <ArrowUpRight size={13} aria-hidden="true" /></span></div>
  </Link>
}

function PlanCard({ plan }: { plan: CreatorSubscriptionPlan }) {
  const price = formatBaseUnits(plan.price_base_units, plan.token_decimals)
  return <Link className="creator-public-card subscription-plan-card" to={`/app/research/plans/${encodeURIComponent(plan.plan_id)}`}>
    <div className="creator-note-row-top"><span className="creator-label">{plan.creator_account}</span><span className="creator-status creator-status-published">ACTIVE</span></div>
    <h3>{plan.title}</h3>
    <p>{plan.description}</p>
    <div className="subscription-plan-meta"><span><CalendarClock size={13} aria-hidden="true" /> {plan.duration_days} days</span><strong>{price} {plan.token_symbol}</strong></div>
    <div className="creator-public-card-meta"><span>{plan.scope.length} research note{plan.scope.length === 1 ? '' : 's'} · terms v{plan.terms_version}</span><span>Review <ArrowUpRight size={13} aria-hidden="true" /></span></div>
  </Link>
}

export function PublicSubscriptionPlans({ limit = 6 }: { limit?: number }) {
  const [state, reload] = useApi(() => api.subscriptionPlans(limit), [limit])
  if (state.status === 'loading') return <section className="creator-public-section"><div className="creator-section-head"><div><span className="creator-label">RESEARCH SUBSCRIPTIONS</span><h2>Loading active plans…</h2></div></div></section>
  if (state.status === 'error') return <section className="creator-public-section"><ErrorState error={state.error} onRetry={reload} /></section>
  if (state.data.data.length === 0) return null
  return <section className="creator-public-section" aria-label="Active creator subscription plans">
    <div className="creator-section-head"><div><span className="creator-label">RESEARCH SUBSCRIPTIONS / TESTNET</span><h2>Manual access to creator research</h2></div></div>
    <div className="creator-public-grid">{state.data.data.map((plan) => <PlanCard key={plan.plan_id} plan={plan} />)}</div>
  </section>
}

export function PublicResearchNotes({ limit = 6 }: { limit?: number }) {
  const [state, reload] = useApi(() => api.creatorPublicNotes(limit), [limit])
  if (state.status === 'loading') return <section className="creator-public-section"><div className="creator-section-head"><div><span className="creator-label">CREATOR RESEARCH</span><h2>Loading published notes…</h2></div></div></section>
  if (state.status === 'error') return <section className="creator-public-section"><ErrorState error={state.error} onRetry={reload} /></section>
  return <section className="creator-public-section" aria-label="Published creator research notes">
    <div className="creator-section-head"><div><span className="creator-label">CREATOR RESEARCH / PUBLIC</span><h2>Notes with a visible evidence trail</h2></div><Link className="creator-note-row-actions" to="/app/studio">Open Creator Studio <ArrowUpRight size={14} aria-hidden="true" /></Link></div>
    {state.data.data.length === 0 ? <p className="creator-muted">No published creator notes yet. The first publication will appear here with its observation cutoff and digests.</p> : <div className="creator-public-grid">{state.data.data.map((note) => <NoteCard key={note.note_id} note={note} />)}</div>}
  </section>
}

function EvidenceLane({ title, items }: { title: string; items: CreatorResearchNote['supporting_evidence'] }) {
  return <section className="creator-evidence-lane"><h2>{title} <span className="creator-hint">({items.length})</span></h2>{items.length === 0 ? <p className="creator-muted">None recorded.</p> : items.map((item, index) => <article className="creator-evidence-item" key={`${item.source_id}-${index}`}><span className="creator-label">{item.source_id} · {item.observed_at}</span><p>{item.claim}</p><a href={item.url} target="_blank" rel="noreferrer">{item.url} <ExternalLink size={12} aria-hidden="true" /></a></article>)}</section>
}

function PremiumUnlock({ note }: { note: CreatorResearchNote }) {
  const { accountId, connect, signMessage, signAndSend } = useWallet()
  const [session, setSession] = useState<StoredCreatorSession | null>(() => readCreatorSession())
  const [premium, setPremium] = useState<CreatorPremiumContent | null>(null)
  const [intent, setIntent] = useState<CreatorPaymentIntent | null>(null)
  const [txHash, setTxHash] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (session && accountId && session.accountId !== accountId) {
      clearCreatorSession()
      setSession(null)
      setPremium(null)
    }
  }, [accountId, session])

  useEffect(() => {
    let live = true
    if (!session) return () => { live = false }
    api.creatorPremium(note.note_id, session.token).then((result) => { if (live) setPremium(result.data) }).catch((reason: unknown) => {
      if (live && (!(reason instanceof ApiError) || ![401, 403, 404].includes(reason.status))) setError(reason instanceof Error ? reason.message : String(reason))
    })
    return () => { live = false }
  }, [note.note_id, session])

  async function verifyWallet() {
    if (!accountId) { connect(); setMessage('Connect a NEAR Testnet wallet before signing the ownership challenge.'); return }
    setBusy(true); setError(null); setMessage(null)
    try {
      const next = await verifyCreatorOwnership(accountId, signMessage)
      setSession(next)
      setMessage(`Wallet ownership verified for ${next.accountId}.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  async function verifyTransaction(hash: string) {
    if (!session || !intent || !hash.trim()) return
    setBusy(true); setError(null); setMessage('Checking finalized NEAR Testnet receipt evidence…')
    try {
      const result = await api.creatorVerifyPayment(session.token, intent.intent_id, hash.trim())
      setIntent(result.data)
      setTxHash(hash.trim())
      if (result.data.status === 'VERIFIED') {
        const unlocked = await api.creatorPremium(note.note_id, session.token, result.data.note_revision)
        setPremium(unlocked.data)
        setMessage('Payment independently verified. The purchased immutable revision is unlocked.')
      } else if (result.data.status === 'PENDING') {
        setMessage('The transaction is not finalized yet. Retry verification after the wallet/explorer shows finality.')
      } else {
        setError(result.data.failure_message ?? 'The payment evidence was rejected. No access was granted.')
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  async function purchase() {
    if (!session) { await verifyWallet(); return }
    setBusy(true); setError(null); setMessage(null)
    try {
      const created = (await api.creatorCreatePaymentIntent(session.token, note.note_id)).data
      setIntent(created)
      if (created.status === 'VERIFIED') {
        const unlocked = await api.creatorPremium(note.note_id, session.token, created.note_revision)
        setPremium(unlocked.data)
        return
      }
      const confirmed = window.confirm(`Approve ${formatBaseUnits(created.amount_base_units, created.token_decimals)} ${created.token_symbol} on NEAR Testnet to ${created.recipient_account} for “${created.note_title}”?\n\nToken contract: ${created.token_contract}\nMemo: ${created.memo}\nGas: ${created.action.gas_tgas} TGas + 1 yocto deposit.\n\nThis is non-refundable in V1. Notch cannot sign or broadcast for you.`)
      if (!confirmed) { setMessage('Purchase cancelled. No wallet transaction was requested.'); return }
      const result = await signAndSend({ receiverId: created.action.receiver_id, calls: [{ methodName: created.action.method_name, args: created.action.args, gasTgas: created.action.gas_tgas, depositYocto: created.action.attached_deposit_yocto }] })
      if (!result.hash) {
        setMessage('The wallet returned without an in-page hash. Paste the finalized Testnet transaction hash below to verify it.')
        return
      }
      await verifyTransaction(result.hash)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setBusy(false) }
  }

  if (!note.premium.enabled) return null
  const price = formatBaseUnits(note.premium.price_base_units, note.premium.token_decimals)
  const currentUnlocked = premium?.revision === note.revision
  return <section className="creator-premium-card" aria-label="Premium research unlock">
    <div className="creator-premium-head"><div><span className="creator-label">PREMIUM RESEARCH / TESTNET</span><h2>{currentUnlocked ? 'Unlocked purchased revision' : 'Unlock the private method'}</h2></div><LockKeyhole size={20} aria-hidden="true" /></div>
    {currentUnlocked && premium ? <div className="creator-premium-body"><p className="creator-label">REVISION {premium.revision} · VERIFIED ACCESS</p><div className="creator-premium-text">{premium.premium.body}</div>{premium.entitlement?.explorer_url && <a className="creator-note-row-actions" href={premium.entitlement.explorer_url} target="_blank" rel="noreferrer">View verified Testnet transaction <ExternalLink size={13} aria-hidden="true" /></a>}</div> : <>
      <p className="creator-muted">The public thesis, evidence, cutoff, and digests remain visible above. The protected body is a separate immutable revision and costs <strong>{price} {note.premium.token_symbol}</strong>.{premium && ` You have a verified entitlement for revision ${premium.revision}; this page shows current revision ${note.revision}.`}</p>
      <p className="creator-hint">Payment is Testnet-only. The server will verify the finalized token transfer, exact buyer, recipient, amount, memo, receipt, and unique transaction evidence before unlocking.</p>
      {!session && <button className="btn btn-accent" type="button" onClick={verifyWallet} disabled={busy}>{busy ? 'Waiting for wallet…' : accountId ? 'Verify wallet to unlock' : 'Connect wallet to unlock'}</button>}
      {session && !intent && <button className="btn btn-accent" type="button" onClick={purchase} disabled={busy}>{busy ? 'Preparing wallet approval…' : `Purchase for ${price} ${note.premium.token_symbol}`}</button>}
      {intent && intent.status !== 'VERIFIED' && <div className="creator-payment-panel"><div className="creator-payment-grid"><span>Network<strong>{intent.network}</strong></span><span>Token<strong>{intent.token_contract}</strong></span><span>Recipient<strong>{intent.recipient_account}</strong></span><span>Amount<strong>{price} {intent.token_symbol}</strong></span><span>Gas<strong>{intent.action.gas_tgas} TGas + {intent.action.attached_deposit_yocto} yocto</strong></span><span>Status<strong>{intent.status}</strong></span></div><p className="creator-hint">Approve the exact transfer only after checking the note, token contract, recipient, memo, amount, and Testnet network. Your wallet needs NEAR for gas; the recipient must be registered for token storage.</p><label>Finalized Testnet transaction hash<input className="creator-payment-input" value={txHash} onChange={(e) => setTxHash(e.target.value)} placeholder="Paste the wallet transaction hash" /></label><button className="btn btn-accent" type="button" onClick={() => verifyTransaction(txHash)} disabled={busy || !txHash.trim() || intent.status === 'FAILED' || intent.status === 'EXPIRED'}>{busy ? 'Verifying…' : 'Retry verification'}</button>{(intent.status === 'FAILED' || intent.status === 'EXPIRED') && <button className="btn btn-quiet" type="button" onClick={() => { setIntent(null); setTxHash(''); setError(null); setMessage('Ready to create a fresh payment intent.') }}>Start a new payment intent</button>}</div>}
    </>}
    {message && <div className="creator-notice" role="status">{message}</div>}
    {error && <div className="creator-error" role="alert">{error}</div>}
  </section>
}

export function ResearchNote() {
  const { id } = useParams()
  const [state, reload] = useApi(() => api.creatorPublicNote(id ?? ''), [id])
  if (state.status === 'loading') return <SkeletonList n={2} h={180} />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={reload} />
  const note = state.data.data
  return <div className="creator-detail">
    <header className="creator-detail-card">
      <div className="creator-detail-meta"><span className="creator-label">CREATOR RESEARCH NOTE / V1</span><span><ShieldCheck size={13} aria-hidden="true" /> Verified wallet owner</span><span>{note.position} · revision {note.revision}</span></div>
      <h1>{note.title}</h1>
      <p className="creator-detail-lede">{note.thesis}</p>
      <div className="creator-detail-meta"><span>By <Link to="/app/discover">{note.creator_account}</Link></span><span>Reference: {note.reference.label}</span><span>Cutoff: {note.observation_cutoff}</span></div>
    </header>
    <div className="creator-detail-columns">
      <div className="creator-detail-card"><EvidenceLane title="Supporting evidence" items={note.supporting_evidence} /><div style={{ height: 24 }} /><EvidenceLane title="Contradictory evidence" items={note.contradictory_evidence} /></div>
      <aside className="creator-detail-card creator-provenance"><div className="creator-section-head"><div><span className="creator-label">PROVENANCE</span><h2>Inspect the revision</h2></div><FileText size={18} aria-hidden="true" /></div><div className="creator-provenance-row"><span className="creator-label">Content digest</span><strong>{note.content_digest}</strong></div><div className="creator-provenance-row"><span className="creator-label">Evidence digest</span><strong>{note.evidence_digest}</strong></div><div className="creator-provenance-row"><span className="creator-label">Sources</span><strong>{note.source_ids.join(', ')}</strong></div>{note.premium.enabled && <div className="creator-provenance-row"><span className="creator-label">Premium offer</span><strong>{formatBaseUnits(note.premium.price_base_units, note.premium.token_decimals)} {note.premium.token_symbol} · body digest {note.premium.body_digest}</strong></div>}{note.strategy_reference && <div className="creator-provenance-row"><span className="creator-label">Strategy reference · as supplied</span><strong>{note.strategy_reference.id} / {note.strategy_reference.revision_hash}</strong></div>}<div><span className="creator-label">Revision history</span><div className="creator-revision-list">{(note.revision_history ?? []).map((revision) => <div className="creator-revision" key={revision.revision}><span>rev {revision.revision} · {revision.status}</span><span>{revision.content_digest.slice(0, 16)}…</span></div>)}</div></div><p className="creator-muted">Publication proves a signed account controlled the publishing key. Premium access is granted only by server-verified Testnet receipt evidence.</p></aside>
    </div>
    <PremiumUnlock note={note} />
  </div>
}
