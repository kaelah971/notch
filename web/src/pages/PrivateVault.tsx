import { useEffect, useState, type FormEvent } from 'react'
import { Check, FilePenLine, LockKeyhole, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { PrivateResearchRecord } from '../api/types'
import { useApi } from '../api/useApi'
import { clearCreatorSession, readCreatorSession, verifyCreatorOwnership, type StoredCreatorSession } from '../creator/session'
import { useWallet } from '../wallet/WalletProvider'
import './CreatorStudio.css'

type VaultPrefill = {
  marketId?: string
  title?: string
  thesis?: string
  sourceReferences?: string[]
}

const emptyVault = { data: [] as PrivateResearchRecord[], meta: { count: 0, private: true } }

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function PrivateVault() {
  const { accountId, connect, signMessage } = useWallet()
  const location = useLocation()
  const prefill = (location.state as VaultPrefill | null) ?? null
  const queryMarket = new URLSearchParams(location.search).get('market_id') ?? ''
  const [session, setSession] = useState<StoredCreatorSession | null>(() => readCreatorSession())
  const [identityState, setIdentityState] = useState<'idle' | 'working' | 'error'>('idle')
  const [identityError, setIdentityError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [title, setTitle] = useState(prefill?.title ?? '')
  const [thesis, setThesis] = useState(prefill?.thesis ?? '')
  const [predictedOutcome, setPredictedOutcome] = useState('')
  const [confidence, setConfidence] = useState('')
  const [marketId, setMarketId] = useState(prefill?.marketId ?? queryMarket)
  const [sourceReferences, setSourceReferences] = useState((prefill?.sourceReferences ?? []).join('\n'))
  const [invalidationCondition, setInvalidationCondition] = useState('')

  const vaultState = useApi(() => session ? api.vaultMine(session.token) : Promise.resolve(emptyVault), [session?.token])

  useEffect(() => {
    if (session && accountId && session.accountId !== accountId) {
      clearCreatorSession()
      setSession(null)
      setIdentityState('idle')
      setNotice('The connected wallet changed. Verify the new wallet to reopen private research.')
    }
  }, [accountId, session])

  function resetForm() {
    setEditingId(null)
    setTitle('')
    setThesis('')
    setPredictedOutcome('')
    setConfidence('')
    setMarketId('')
    setSourceReferences('')
    setInvalidationCondition('')
    setSaveError(null)
  }

  function editRecord(record: PrivateResearchRecord) {
    setEditingId(record.research_id)
    setTitle(record.title)
    setThesis(record.thesis)
    setPredictedOutcome(record.predicted_outcome)
    setConfidence(record.confidence == null ? '' : String(record.confidence))
    setMarketId(record.market_id ?? '')
    setSourceReferences(record.source_references.join('\n'))
    setInvalidationCondition(record.invalidation_condition)
    setSaveError(null)
    setNotice(`Editing private research updated ${formatDate(record.updated_at)}.`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function verifyIdentity() {
    if (!accountId) {
      connect()
      setIdentityError('Connect a NEAR Testnet wallet before signing the ownership challenge.')
      return
    }
    setIdentityState('working')
    setIdentityError(null)
    try {
      const next = await verifyCreatorOwnership(accountId, signMessage)
      setSession(next)
      setIdentityState('idle')
      setNotice(`Private vault unlocked for ${next.accountId}.`)
    } catch (error) {
      setIdentityState('error')
      setIdentityError(errorText(error))
    }
  }

  async function saveResearch(event: FormEvent) {
    event.preventDefault()
    if (!session) {
      setSaveError('Verify wallet ownership before saving private research.')
      return
    }
    setSaveError(null)
    setNotice(null)
    const rawConfidence = confidence.trim()
    const payload: Record<string, unknown> = {
      market_id: marketId.trim() || null,
      title,
      thesis,
      predicted_outcome: predictedOutcome,
      confidence: rawConfidence ? Number(rawConfidence) : null,
      source_references: sourceReferences.split('\n').map((item) => item.trim()).filter(Boolean),
      invalidation_condition: invalidationCondition,
    }
    try {
      const result = editingId
        ? await api.vaultUpdate(session.token, editingId, payload)
        : await api.vaultCreate(session.token, payload)
      setEditingId(result.data.research_id)
      setNotice(`Saved privately · updated ${formatDate(result.data.updated_at)}.`)
      vaultState[1]()
    } catch (error) {
      setSaveError(errorText(error))
    }
  }

  async function deleteResearch(researchId: string) {
    if (!session || !window.confirm('Delete this private research permanently?')) return
    setSaveError(null)
    try {
      await api.vaultDelete(session.token, researchId)
      if (editingId === researchId) resetForm()
      setNotice('Private research deleted. It was not published or sent on-chain.')
      vaultState[1]()
    } catch (error) {
      setSaveError(errorText(error))
    }
  }

  const records = vaultState[0].status === 'ok' ? vaultState[0].data.data : []

  return (
    <>
      <header className="page-head creator-head">
        <div>
          <p className="eyebrow">PRIVATE RESEARCH VAULT / V1</p>
          <h1>Keep the thesis. Revisit the evidence.</h1>
          <p>Save a private hypothesis with its market context, source references, confidence, and invalidation condition. This is owner-restricted application storage — not end-to-end encryption or public publishing.</p>
        </div>
        <div className="creator-proof-badge"><LockKeyhole size={18} aria-hidden="true" /><span>PRIVATE · owner-only</span></div>
      </header>

      <section className="creator-identity-panel">
        <div className="creator-identity-icon"><ShieldCheck size={20} aria-hidden="true" /></div>
        <div className="creator-identity-copy">
          <span className="creator-label">NEAR WALLET OWNERSHIP</span>
          <strong>{session ? `Vault unlocked for ${session.accountId}` : accountId ? `Wallet connected · ${accountId}` : 'Connect a wallet to open your vault'}</strong>
          <p>The existing NEP-413 challenge is signed in your wallet. The API derives the owner from the verified session; private research is never written on-chain or sent to AI automatically.</p>
          {identityError && <span className="creator-error">{identityError}</span>}
        </div>
        <button className="btn creator-verify" type="button" onClick={verifyIdentity} disabled={identityState === 'working'}>
          {identityState === 'working' ? 'Waiting for wallet…' : session ? 'Re-verify wallet' : accountId ? 'Unlock vault' : 'Connect wallet'}
        </button>
      </section>

      <div className="creator-layout">
        <form className="creator-editor" onSubmit={saveResearch}>
          <div className="creator-section-head"><div><span className="creator-label">PRIVATE THESIS</span><h2>{editingId ? 'Edit saved research' : 'Save a new hypothesis'}</h2></div>{editingId && <button type="button" className="btn btn-quiet" onClick={resetForm}>New research</button>}</div>
          <label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} placeholder="A precise research question or thesis" required /></label>
          <label>Thesis / hypothesis<textarea value={thesis} onChange={(event) => setThesis(event.target.value)} maxLength={10000} rows={7} placeholder="What do you believe, and why? Keep the reasoning private until you choose to revisit it." required /></label>
          <div className="creator-form-grid">
            <label>Predicted outcome or stance<input value={predictedOutcome} onChange={(event) => setPredictedOutcome(event.target.value)} maxLength={160} placeholder="UP, DOWN, or a falsifiable outcome" required /></label>
            <label>Confidence <span className="creator-optional">0–100</span><input inputMode="decimal" type="number" min="0" max="100" step="0.1" value={confidence} onChange={(event) => setConfidence(event.target.value)} placeholder="Optional" /></label>
          </div>
          <div className="creator-subhead"><span className="creator-label">MARKET CONTEXT</span><span className="creator-hint">Optional. The vault shows the current market state when this reference still exists.</span></div>
          <label>Market ID <span className="creator-optional">optional</span><input value={marketId} onChange={(event) => setMarketId(event.target.value)} maxLength={200} placeholder="s3b-future-btc-…" /></label>
          <label>Supporting source references <span className="creator-optional">one per line</span><textarea value={sourceReferences} onChange={(event) => setSourceReferences(event.target.value)} maxLength={10000} rows={4} placeholder="Source ID, URL, or evidence reference" /></label>
          <label>Invalidation condition<textarea value={invalidationCondition} onChange={(event) => setInvalidationCondition(event.target.value)} maxLength={2000} rows={3} placeholder="What would prove this thesis wrong?" required /></label>
          {saveError && <div className="creator-error creator-alert" role="alert">{saveError}</div>}
          {notice && <div className="creator-notice" role="status"><Check size={15} aria-hidden="true" />{notice}</div>}
          <div className="creator-actions"><button className="btn btn-accent" type="submit" disabled={!session}>{editingId ? 'Save changes privately' : 'Save privately'}</button></div>
        </form>

        <aside className="creator-sidebar">
          <div className="creator-side-card">
            <div className="creator-section-head"><div><span className="creator-label">YOUR PRIVATE RESEARCH</span><h2>Return to a thesis</h2></div><button className="icon-btn" type="button" onClick={() => vaultState[1]()} aria-label="Refresh private research"><RefreshCw size={16} aria-hidden="true" /></button></div>
            {!session ? <p className="creator-muted">Unlock the vault to see research owned by this wallet.</p> : vaultState[0].status === 'loading' ? <p className="creator-muted">Loading your private research…</p> : vaultState[0].status === 'error' ? <p className="creator-error">{vaultState[0].error.message}</p> : records.length === 0 ? <p className="creator-muted">Nothing saved yet. Use “Save privately” from a market research panel or start a thesis here.</p> : <div className="creator-note-list">{records.map((record) => <article className={`creator-note-row ${editingId === record.research_id ? 'is-selected' : ''}`} key={record.research_id}><div className="creator-note-row-top"><strong>{record.title}</strong><span className="creator-status creator-status-draft">PRIVATE</span></div><span className="creator-note-meta mono">{record.market?.status ?? 'No market'} · updated {formatDate(record.updated_at)}</span><p className="creator-muted">Invalidated if: {record.invalidation_condition}</p><div className="creator-note-row-actions"><button type="button" onClick={() => editRecord(record)}><FilePenLine size={14} aria-hidden="true" /> Open</button><button type="button" onClick={() => deleteResearch(record.research_id)}><Trash2 size={14} aria-hidden="true" /> Delete</button></div></article>)}</div>}
          </div>
          <div className="creator-side-card creator-limit-card"><span className="creator-label">PRIVACY BOUNDARY</span><p>Only the verified wallet session can list, open, edit, or delete these records. Private research is not included in Passport, Pulse, discovery, creator feeds, or public research endpoints.</p></div>
        </aside>
      </div>
    </>
  )
}
