import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Check, ExternalLink, FilePenLine, LockKeyhole, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { CreatorPayoutStatus, CreatorPurchases, CreatorResearchNote, CreatorSubscriptionPlan, CreatorSubscriptions } from '../api/types'
import { useApi } from '../api/useApi'
import { useWallet } from '../wallet/WalletProvider'
import { clearCreatorSession, readCreatorSession, verifyCreatorOwnership, type StoredCreatorSession } from '../creator/session'
import './CreatorStudio.css'

const DEFAULT_SOURCE_URL = 'https://pageviews.wmcloud.org/'
const emptyMine = { data: [] as CreatorResearchNote[], meta: { count: 0, private: true } }
const emptyPayout: CreatorPayoutStatus = { configured: false, creator_account: '', network: 'testnet', token_contract: null, payout_account: null, token_symbol: null, token_decimals: null, storage_registered: false, verified_at: null }
const emptyPurchases: CreatorPurchases = { buyer_entitlements: [], creator_sales: [] }
const emptyPlans = { data: [] as CreatorSubscriptionPlan[], meta: { count: 0, private: true } }
const emptySubscriptions: CreatorSubscriptions = { subscriber_subscriptions: [], creator_subscriptions: [] }

function formatBaseUnits(value: string | null, decimals: number | null) {
  if (!value || decimals == null) return ''
  const padded = value.padStart(decimals + 1, '0')
  const split = padded.length - decimals
  const whole = padded.slice(0, split)
  const fraction = padded.slice(split).replace(/0+$/, '')
  return fraction ? `${whole}.${fraction}` : whole
}

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
}

function NoteStatus({ status }: { status: string }) {
  return <span className={`creator-status creator-status-${status.toLowerCase()}`}>{status}</span>
}

export function CreatorStudio() {
  const { accountId, connect, signMessage } = useWallet()
  const [session, setSession] = useState<StoredCreatorSession | null>(() => readCreatorSession())
  const [identityState, setIdentityState] = useState<'idle' | 'working' | 'verified' | 'error'>('idle')
  const [identityError, setIdentityError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [thesis, setThesis] = useState('')
  const [position, setPosition] = useState<'UP' | 'DOWN' | 'NEUTRAL'>('UP')
  const [referenceId, setReferenceId] = useState('')
  const [referenceLabel, setReferenceLabel] = useState('')
  const [cutoff, setCutoff] = useState(() => new Date(Date.now() - 86_400_000).toISOString())
  const [sourceId, setSourceId] = useState('wikimedia-pageviews-v1')
  const [sourceUrl, setSourceUrl] = useState(DEFAULT_SOURCE_URL)
  const [claim, setClaim] = useState('')
  const [counterClaim, setCounterClaim] = useState('')
  const [strategyId, setStrategyId] = useState('')
  const [strategyHash, setStrategyHash] = useState('')
  const [premiumEnabled, setPremiumEnabled] = useState(false)
  const [premiumBody, setPremiumBody] = useState('')
  const [premiumPrice, setPremiumPrice] = useState('')
  const [payoutBusy, setPayoutBusy] = useState(false)
  const [payoutError, setPayoutError] = useState<string | null>(null)
  const [planId, setPlanId] = useState<string | null>(null)
  const [planTitle, setPlanTitle] = useState('')
  const [planDescription, setPlanDescription] = useState('')
  const [planDuration, setPlanDuration] = useState<7 | 30>(7)
  const [planPrice, setPlanPrice] = useState('')
  const [planScope, setPlanScope] = useState<string[]>([])
  const [planError, setPlanError] = useState<string | null>(null)

  const scoutState = useApi(() => api.scout('all', 12), [])
  const mineState = useApi(() => session ? api.creatorMine(session.token) : Promise.resolve(emptyMine), [session?.token])
  const payoutState = useApi(() => session ? api.creatorPayout(session.token) : Promise.resolve({ data: emptyPayout }), [session?.token])
  const purchasesState = useApi(() => session ? api.creatorPurchases(session.token) : Promise.resolve({ data: emptyPurchases }), [session?.token])
  const plansState = useApi(() => session ? api.creatorPlans(session.token) : Promise.resolve(emptyPlans), [session?.token])
  const subscriptionsState = useApi(() => session ? api.subscriptions(session.token) : Promise.resolve({ data: emptySubscriptions }), [session?.token])
  const candidates = scoutState[0].status === 'ok' ? scoutState[0].data.data : []

  useEffect(() => {
    if (session && accountId && session.accountId !== accountId) {
      clearCreatorSession()
      setSession(null)
      setIdentityState('idle')
    }
  }, [accountId, session])

  useEffect(() => {
    if (!referenceId && candidates[0]) {
      setReferenceId(candidates[0].candidate_id)
      setReferenceLabel(candidates[0].topic)
    }
  }, [candidates, referenceId])

  const activeNote = useMemo(
    () => mineState[0].status === 'ok' ? mineState[0].data.data.find((item) => item.note_id === selectedId) ?? null : null,
    [mineState, selectedId],
  )

  function clearForm() {
    setEditingId(null)
    setSelectedId(null)
    setTitle('')
    setThesis('')
    setPosition('UP')
    setClaim('')
    setCounterClaim('')
    setStrategyId('')
    setStrategyHash('')
    setPremiumEnabled(false)
    setPremiumBody('')
    setPremiumPrice('')
  }

  function editNote(note: CreatorResearchNote) {
    setEditingId(note.note_id)
    setSelectedId(note.note_id)
    setTitle(note.title)
    setThesis(note.thesis)
    setPosition(note.position)
    setReferenceId(note.reference.id)
    setReferenceLabel(note.reference.label)
    setCutoff(note.observation_cutoff)
    const first = note.supporting_evidence[0]
    setSourceId(first?.source_id ?? 'wikimedia-pageviews-v1')
    setSourceUrl(first?.url ?? DEFAULT_SOURCE_URL)
    setClaim(first?.claim ?? '')
    setCounterClaim(note.contradictory_evidence[0]?.claim ?? '')
    setStrategyId(note.strategy_reference?.id ?? '')
    setStrategyHash(note.strategy_reference?.revision_hash ?? '')
    setPremiumEnabled(note.premium.enabled)
    setPremiumBody(note.premium.body ?? '')
    setPremiumPrice(formatBaseUnits(note.premium.price_base_units, note.premium.token_decimals))
    setNotice(`Editing revision ${note.revision} of ${note.note_id}. Publishing creates a new immutable revision.`)
  }

  async function verifyIdentity() {
    if (!accountId) { connect(); setIdentityError('Connect a NEAR Testnet wallet before signing the ownership challenge.'); return }
    setIdentityState('working')
    setIdentityError(null)
    try {
      const next = await verifyCreatorOwnership(accountId, signMessage)
      setSession(next)
      setIdentityState('verified')
      setNotice(`Wallet ownership verified for ${next.accountId}.`)
    } catch (error) {
      setIdentityState('error')
      setIdentityError(errorText(error))
    }
  }

  async function revokeIdentity() {
    if (!session) return
    setIdentityError(null)
    try {
      await api.creatorRevoke(session.token)
    } catch (error) {
      setIdentityError(errorText(error))
      return
    }
    clearCreatorSession()
    setSession(null)
    setIdentityState('idle')
    setNotice('Creator Studio session revoked on the server.')
  }

  async function configurePayout() {
    if (!session) { setPayoutError('Verify wallet ownership before configuring a payout account.'); return }
    setPayoutBusy(true)
    setPayoutError(null)
    try {
      await api.creatorConfigurePayout(session.token, session.accountId)
      setNotice('Verified Testnet payout account and token storage registration.')
      payoutState[1]()
    } catch (error) {
      setPayoutError(errorText(error))
    } finally {
      setPayoutBusy(false)
    }
  }

  function editPlan(plan: CreatorSubscriptionPlan) {
    setPlanId(plan.plan_id)
    setPlanTitle(plan.title)
    setPlanDescription(plan.description)
    setPlanDuration(plan.duration_days === 30 ? 30 : 7)
    setPlanPrice(formatBaseUnits(plan.price_base_units, plan.token_decimals))
    setPlanScope(plan.scope_note_ids ?? plan.scope.map((note) => note.note_id))
    setPlanError(null)
    setNotice(`Editing subscription terms v${plan.terms_version}. Saving changed terms creates a new immutable plan version.`)
  }

  function clearPlan() {
    setPlanId(null)
    setPlanTitle('')
    setPlanDescription('')
    setPlanDuration(7)
    setPlanPrice('')
    setPlanScope([])
    setPlanError(null)
  }

  async function savePlan(event: FormEvent) {
    event.preventDefault()
    if (!session) { setPlanError('Verify wallet ownership before configuring a subscription plan.'); return }
    if (planScope.length === 0) { setPlanError('Select at least one published premium note for this plan.'); return }
    setPlanError(null)
    try {
      const body = { title: planTitle, description: planDescription, duration_days: planDuration, price: planPrice, note_ids: planScope }
      const result = planId ? await api.creatorPlanUpdate(session.token, planId, body) : await api.creatorPlanCreate(session.token, body)
      setPlanId(result.data.plan_id)
      setNotice(`Subscription plan ${result.data.title} saved at terms version ${result.data.terms_version}.`)
      plansState[1]()
    } catch (error) { setPlanError(errorText(error)) }
  }

  async function togglePlan(plan: CreatorSubscriptionPlan) {
    if (!session) return
    setPlanError(null)
    try {
      const result = await api.creatorPlanUpdate(session.token, plan.plan_id, { status: plan.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE' })
      setNotice(`${result.data.title} is now ${result.data.status.toLowerCase()}.`)
      plansState[1]()
    } catch (error) { setPlanError(errorText(error)) }
  }

  async function saveDraft(event: FormEvent) {
    event.preventDefault()
    if (!session) { setSaveError('Verify wallet ownership before saving a research note.'); return }
    if (!referenceId) { setSaveError('Choose a source-backed Scout topic or enter a valid market reference.'); return }
    setSaveError(null)
    setNotice(null)
    const payload: Record<string, unknown> = {
      title, thesis, position,
      reference: { kind: 'topic', id: referenceId, label: referenceLabel || referenceId },
      observation_cutoff: cutoff,
      supporting_evidence: claim ? [{ source_id: sourceId, url: sourceUrl, observed_at: cutoff, claim }] : [],
      contradictory_evidence: counterClaim ? [{ source_id: sourceId, url: sourceUrl, observed_at: cutoff, claim: counterClaim }] : [],
      strategy_reference: strategyId && strategyHash ? { id: strategyId, revision_hash: strategyHash } : null,
      evaluation_reference: null,
      premium: premiumEnabled ? { enabled: true, body: premiumBody, price: premiumPrice } : { enabled: false },
    }
    try {
      const result = editingId
        ? await api.creatorUpdate(session.token, editingId, payload)
        : await api.creatorCreate(session.token, payload)
      setSelectedId(result.data.note_id)
      setEditingId(result.data.note_id)
      setNotice(`${result.data.status === 'DRAFT' ? 'Draft saved' : 'Revision saved'} · ${result.data.content_digest}`)
      mineState[1]()
    } catch (error) { setSaveError(errorText(error)) }
  }

  async function publishNote(noteId: string) {
    if (!session) return
    setSaveError(null)
    try {
      const result = await api.creatorPublish(session.token, noteId)
      setNotice(`Published revision ${result.data.revision}. Public readers can inspect its evidence and digests.`)
      mineState[1]()
    } catch (error) { setSaveError(errorText(error)) }
  }

  async function withdrawNote(noteId: string) {
    if (!session || !window.confirm('Withdraw this public note? Its revision history remains inspectable to the creator.')) return
    try {
      await api.creatorWithdraw(session.token, noteId, 'Withdrawn by creator')
      setNotice('Note withdrawn. It is no longer in public discovery.')
      mineState[1]()
    } catch (error) { setSaveError(errorText(error)) }
  }

  return (
    <>
      <header className="page-head creator-head">
        <div>
          <p className="eyebrow">CREATOR STUDIO / RESEARCH NOTES V1</p>
          <h1>Publish the work behind a forecast.</h1>
          <p>Write a source-backed research note, preserve the observation cutoff, and publish a verifiable revision without giving Notch custody of your wallet.</p>
        </div>
        <div className="creator-proof-badge"><ShieldCheck size={18} aria-hidden="true" /><span>Read-only research · no payments</span></div>
      </header>

      <section className="creator-identity-panel">
        <div className="creator-identity-icon"><LockKeyhole size={20} aria-hidden="true" /></div>
        <div className="creator-identity-copy">
          <span className="creator-label">OWNERSHIP VERIFICATION</span>
          <strong>{session ? `Verified as ${session.accountId}` : accountId ? `Wallet connected · ${accountId}` : 'Connect a wallet to claim authorship'}</strong>
          <p>A short NEP-413 challenge is signed in your wallet. The API checks the public key against a final NEAR Testnet access-key lookup. It never receives a private key or transaction approval.</p>
          {identityError && <span className="creator-error">{identityError}</span>}
        </div>
        <div className="creator-identity-actions"><button className="btn creator-verify" onClick={verifyIdentity} disabled={identityState === 'working'}>
          {identityState === 'working' ? 'Waiting for wallet…' : session ? 'Re-verify wallet' : accountId ? 'Verify ownership' : 'Connect wallet'}
        </button>{session && <button className="btn btn-quiet" type="button" onClick={revokeIdentity}>Revoke session</button>}</div>
      </section>

      <div className="creator-layout">
        <form className="creator-editor" onSubmit={saveDraft}>
          <div className="creator-section-head"><div><span className="creator-label">DRAFTING CANVAS</span><h2>{editingId ? 'Revise a note' : 'Start a research note'}</h2></div>{editingId && <button type="button" className="btn btn-quiet" onClick={clearForm}>New note</button>}</div>
          <label>Title<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={140} placeholder="A precise, falsifiable research title" required /></label>
          <label>Thesis<textarea value={thesis} onChange={(e) => setThesis(e.target.value)} maxLength={4000} rows={5} placeholder="What do the observations support, and what do they not support?" required /></label>
          <div className="creator-form-grid">
            <label>Position<select value={position} onChange={(e) => setPosition(e.target.value as typeof position)}><option value="UP">UP</option><option value="DOWN">DOWN</option><option value="NEUTRAL">NEUTRAL</option></select></label>
            <label>Observation cutoff<input type="datetime-local" value={cutoff.slice(0, 16)} onChange={(e) => setCutoff(new Date(e.target.value).toISOString())} required /><span className="creator-hint">Evidence after this timestamp is rejected.</span></label>
          </div>
          <div className="creator-subhead"><span className="creator-label">REFERENCE ANCHOR</span><span className="creator-hint">Choose a stored Radar topic; market references are supported by the API.</span></div>
          <div className="creator-form-grid">
            <label>Topic<select value={referenceId} onChange={(e) => { const item = candidates.find((candidate) => candidate.candidate_id === e.target.value); setReferenceId(e.target.value); setReferenceLabel(item?.topic ?? e.target.value) }}><option value="">Select an observed topic</option>{candidates.map((candidate) => <option key={candidate.candidate_id} value={candidate.candidate_id}>{candidate.topic}</option>)}</select></label>
            <label>Reference label<input value={referenceLabel} onChange={(e) => setReferenceLabel(e.target.value)} maxLength={240} placeholder="Displayed topic label" /></label>
          </div>
          <div className="creator-subhead"><span className="creator-label">SOURCE-BACKED OBSERVATIONS</span><span className="creator-hint">URLs are stored exactly and only HTTPS source IDs from the catalog are accepted.</span></div>
          <div className="creator-form-grid">
            <label>Source ID<input value={sourceId} onChange={(e) => setSourceId(e.target.value)} placeholder="wikimedia-pageviews-v1" required /></label>
            <label>Source URL<input type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder={DEFAULT_SOURCE_URL} required /></label>
          </div>
          <label>Supporting observation<textarea value={claim} onChange={(e) => setClaim(e.target.value)} maxLength={800} rows={3} placeholder="What did the source actually observe?" required /></label>
          <label>Contradictory observation <span className="creator-optional">optional</span><textarea value={counterClaim} onChange={(e) => setCounterClaim(e.target.value)} maxLength={800} rows={2} placeholder="What weakens or qualifies the thesis?" /></label>
          <div className="creator-subhead"><span className="creator-label">PREMIUM RESEARCH OFFER</span><span className="creator-hint">Testnet-only unlock; public evidence and preview remain visible.</span></div>
          <label className="creator-check"><input type="checkbox" checked={premiumEnabled} onChange={(e) => setPremiumEnabled(e.target.checked)} /> Offer protected research body</label>
          {premiumEnabled && <>
            <label>Premium body<textarea value={premiumBody} onChange={(e) => setPremiumBody(e.target.value)} maxLength={50000} rows={7} placeholder="The private method, assumptions, and deeper analysis readers unlock after verified payment." required /></label>
            <label>Price in {payoutState[0].status === 'ok' ? payoutState[0].data.data.token_symbol ?? 'configured Testnet token' : 'configured Testnet token'}<input inputMode="decimal" value={premiumPrice} onChange={(e) => setPremiumPrice(e.target.value)} placeholder="1.25" required /><span className="creator-hint">The server converts this decimal using verified token metadata and stores exact base units.</span></label>
          </>}
          <div className="creator-subhead"><span className="creator-label">OPTIONAL LOCAL REFERENCES</span><span className="creator-hint">Hashes are preserved as supplied; V1 does not pretend to verify browser-local artifacts.</span></div>
          <div className="creator-form-grid">
            <label>Strategy ID<input value={strategyId} onChange={(e) => setStrategyId(e.target.value)} placeholder="local strategy id" /></label>
            <label>Strategy revision hash<input value={strategyHash} onChange={(e) => setStrategyHash(e.target.value)} placeholder="sha256:…" /></label>
          </div>
          {saveError && <div className="creator-error creator-alert">{saveError}</div>}
          {notice && <div className="creator-notice"><Check size={15} aria-hidden="true" />{notice}</div>}
          <div className="creator-actions"><button className="btn" type="submit" disabled={!session}>{editingId ? 'Save new revision' : 'Save draft'}</button>{editingId && activeNote?.status === 'DRAFT' && <button className="btn btn-accent" type="button" onClick={() => publishNote(editingId)}>Publish verified note</button>}</div>
        </form>

        <aside className="creator-sidebar">
          <div className="creator-side-card">
            <div className="creator-section-head"><div><span className="creator-label">YOUR NOTES</span><h2>Revision ledger</h2></div><button className="icon-btn" onClick={() => mineState[1]()} aria-label="Refresh your notes"><RefreshCw size={16} aria-hidden="true" /></button></div>
            {!session ? <p className="creator-muted">Verify ownership to see private drafts and publication controls.</p> : mineState[0].status === 'loading' ? <p className="creator-muted">Loading local ledger…</p> : mineState[0].status === 'error' ? <p className="creator-error">{mineState[0].error.message}</p> : mineState[0].data.data.length === 0 ? <p className="creator-muted">No drafts yet. Your first saved note will appear here.</p> : <div className="creator-note-list">{mineState[0].data.data.map((note) => <article className={`creator-note-row ${selectedId === note.note_id ? 'is-selected' : ''}`} key={note.note_id} onClick={() => editNote(note)}><div className="creator-note-row-top"><strong>{note.title}</strong><NoteStatus status={note.status} /></div><span className="creator-note-meta mono">rev {note.revision} · {note.content_digest.slice(0, 18)}…</span><div className="creator-note-row-actions"><button type="button" onClick={(e) => { e.stopPropagation(); editNote(note) }}><FilePenLine size={14} aria-hidden="true" /> Edit</button>{note.status === 'DRAFT' && <button type="button" onClick={(e) => { e.stopPropagation(); publishNote(note.note_id) }}>Publish</button>}{note.status === 'PUBLISHED' && <button type="button" onClick={(e) => { e.stopPropagation(); withdrawNote(note.note_id) }}><Trash2 size={14} aria-hidden="true" /> Withdraw</button>}<Link to={`/app/research/notes/${encodeURIComponent(note.note_id)}`} onClick={(e) => e.stopPropagation()}>Inspect <ExternalLink size={13} aria-hidden="true" /></Link></div></article>)}</div>}
          </div>
          {session && <div className="creator-side-card creator-plan-card">
            <div className="creator-section-head"><div><span className="creator-label">RESEARCH SUBSCRIPTIONS</span><h2>Plan terms</h2></div>{planId && <button className="btn btn-quiet" type="button" onClick={clearPlan}>New plan</button>}</div>
            <p className="creator-muted">Plans are fixed-term, versioned, Testnet-only terms. Existing subscribers keep the exact version they paid for.</p>
            {plansState[0].status === 'loading' ? <p className="creator-muted">Loading plans…</p> : plansState[0].status === 'error' ? <p className="creator-error">{plansState[0].error.message}</p> : plansState[0].data.data.length === 0 ? <p className="creator-muted">No subscription plans yet.</p> : <div className="creator-plan-list">{plansState[0].data.data.map((plan) => <div className="creator-plan-row" key={plan.plan_id}><div><strong>{plan.title}</strong><span>v{plan.terms_version} · {plan.duration_days} days · {formatBaseUnits(plan.price_base_units, plan.token_decimals)} {plan.token_symbol} · {plan.subscriber_count} active</span></div><div className="creator-note-row-actions"><button type="button" onClick={() => editPlan(plan)}>Edit</button><button type="button" onClick={() => togglePlan(plan)}>{plan.status === 'ACTIVE' ? 'Deactivate' : 'Activate'}</button></div>{plan.version_history && plan.version_history.length > 1 && <div className="creator-plan-history"><span className="creator-label">TERMS HISTORY</span>{[...plan.version_history].reverse().map((version) => <span key={version.version}>v{version.version} · {version.duration_days}d · {formatBaseUnits(version.price_base_units, version.token_decimals)} {version.token_symbol} · {new Date(version.created_at).toLocaleDateString()}</span>)}</div>}</div>)}</div>}
            <form className="creator-plan-form" onSubmit={savePlan}>
              <label>Plan title<input value={planTitle} onChange={(event) => setPlanTitle(event.target.value)} maxLength={120} placeholder="Research desk access" required /></label>
              <label>Description<textarea value={planDescription} onChange={(event) => setPlanDescription(event.target.value)} maxLength={1200} rows={3} placeholder="What subscriber-only research does this cover?" required /></label>
              <div className="creator-form-grid"><label>Duration<select value={planDuration} onChange={(event) => setPlanDuration(Number(event.target.value) as 7 | 30)}><option value={7}>7 days</option><option value={30}>30 days</option></select></label><label>Price in {payoutState[0].status === 'ok' ? payoutState[0].data.data.token_symbol ?? 'Testnet token' : 'Testnet token'}<input inputMode="decimal" value={planPrice} onChange={(event) => setPlanPrice(event.target.value)} placeholder="2.50" required /></label></div>
              <div><span className="creator-label">SUBSCRIBER-ONLY RESEARCH SCOPE</span><div className="creator-scope-list">{mineState[0].status === 'ok' && mineState[0].data.data.filter((note) => note.status === 'PUBLISHED' && note.premium.enabled).map((note) => <label className="creator-check" key={note.note_id}><input type="checkbox" checked={planScope.includes(note.note_id)} onChange={() => setPlanScope((current) => current.includes(note.note_id) ? current.filter((id) => id !== note.note_id) : [...current, note.note_id])} />{note.title} <span className="creator-hint">rev {note.revision}</span></label>)}</div></div>
              {planError && <div className="creator-error creator-alert">{planError}</div>}
              <button className="btn btn-accent" type="submit" disabled={!session}>{planId ? 'Save new terms version' : 'Publish active plan'}</button>
            </form>
          </div>}
          {session && subscriptionsState[0].status === 'ok' && <div className="creator-side-card">
            <div className="creator-section-head"><div><span className="creator-label">SUBSCRIPTION HISTORY</span><h2>Verified access ledger</h2></div></div>
            {subscriptionsState[0].data.data.creator_subscriptions.length === 0 ? <p className="creator-muted">No verified subscriber terms yet.</p> : <div className="creator-purchase-list">{subscriptionsState[0].data.data.creator_subscriptions.map((subscription) => <div className="creator-purchase" key={subscription.subscription_id}><strong>{subscription.subscriber_account}</strong><span>{subscription.plan_title} · {subscription.status} · through {subscription.expires_at ? new Date(subscription.expires_at).toLocaleDateString() : 'pending'} · {subscription.payments.length} verified payment{subscription.payments.length === 1 ? '' : 's'}</span>{subscription.payments.map((payment) => <a href={payment.explorer_url} target="_blank" rel="noreferrer" key={payment.payment_id}>v{payment.plan_version} · {new Date(payment.granted_at).toLocaleDateString()} · {payment.tx_hash.slice(0, 12)}… <ExternalLink size={11} aria-hidden="true" /></a>)}</div>)}</div>}
          </div>}
          {session && <div className="creator-side-card">
            <div className="creator-section-head"><div><span className="creator-label">PAYMENT DESTINATION</span><h2>Verified Testnet payout</h2></div><ShieldCheck size={18} aria-hidden="true" /></div>
            {payoutState[0].status === 'loading' ? <p className="creator-muted">Checking token metadata and storage registration…</p> : payoutState[0].status === 'error' ? <p className="creator-error">{payoutState[0].error.message}</p> : payoutState[0].data.data.configured ? <><p className="creator-muted">{payoutState[0].data.data.payout_account} receives {payoutState[0].data.data.token_symbol} on NEAR Testnet. The account is the currently authenticated wallet and was rechecked against its access key.</p><button className="btn btn-quiet" type="button" onClick={configurePayout} disabled={payoutBusy}>{payoutBusy ? 'Rechecking…' : 'Recheck payout account'}</button></> : <><p className="creator-muted">Configure your own authenticated wallet as the receiving account before publishing a premium revision. Notch never becomes the recipient.</p><button className="btn btn-accent" type="button" onClick={configurePayout} disabled={payoutBusy}>{payoutBusy ? 'Checking token…' : 'Configure payout account'}</button></>}
            {payoutError && <div className="creator-error creator-alert">{payoutError}</div>}
          </div>}
          {session && purchasesState[0].status === 'ok' && <div className="creator-side-card">
            <div className="creator-section-head"><div><span className="creator-label">PURCHASE RECORDS</span><h2>Verified sales</h2></div></div>
            {purchasesState[0].data.data.creator_sales.length === 0 ? <p className="creator-muted">No verified Testnet purchases yet. This ledger never invents sales or revenue.</p> : <div className="creator-purchase-list">{purchasesState[0].data.data.creator_sales.map((sale) => <div className="creator-purchase" key={sale.entitlement_id}><strong>{sale.buyer_account}</strong><span>rev {sale.note_revision} · {sale.amount_base_units ?? '—'} {sale.token_symbol ?? ''} · <a href={sale.explorer_url} target="_blank" rel="noreferrer">verified tx ↗</a></span></div>)}</div>}
          </div>}
          <div className="creator-side-card creator-limit-card"><span className="creator-label">V1 IDENTITY LIMIT</span><p>Wallet ownership proves control of the signing key at verification time. It does not prove a legal name, editorial quality, or that a human wrote every sentence.</p></div>
        </aside>
      </div>
    </>
  )
}
