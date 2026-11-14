import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Check, ExternalLink, FilePenLine, LockKeyhole, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { CreatorResearchNote } from '../api/types'
import { useApi } from '../api/useApi'
import { useWallet } from '../wallet/WalletProvider'
import './CreatorStudio.css'

const SESSION_KEY = 'notch.creator-studio.session.v1'
const DEFAULT_SOURCE_URL = 'https://pageviews.wmcloud.org/'
const emptyMine = { data: [] as CreatorResearchNote[], meta: { count: 0, private: true } }

type StoredSession = { token: string; accountId: string; expiresAt: string }

function readSession(): StoredSession | null {
  try {
    const value = JSON.parse(localStorage.getItem(SESSION_KEY) ?? 'null') as StoredSession | null
    if (!value?.token || !value.accountId || Date.parse(value.expiresAt) <= Date.now()) return null
    return value
  } catch { return null }
}

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value)
  return Uint8Array.from(binary, (char) => char.charCodeAt(0))
}

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
}

function NoteStatus({ status }: { status: string }) {
  return <span className={`creator-status creator-status-${status.toLowerCase()}`}>{status}</span>
}

export function CreatorStudio() {
  const { accountId, connect, signMessage } = useWallet()
  const [session, setSession] = useState<StoredSession | null>(() => readSession())
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

  const scoutState = useApi(() => api.scout('all', 12), [])
  const mineState = useApi(() => session ? api.creatorMine(session.token) : Promise.resolve(emptyMine), [session?.token])
  const candidates = scoutState[0].status === 'ok' ? scoutState[0].data.data : []

  useEffect(() => {
    if (session && accountId && session.accountId !== accountId) {
      localStorage.removeItem(SESSION_KEY)
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
    setNotice(`Editing revision ${note.revision} of ${note.note_id}. Publishing creates a new immutable revision.`)
  }

  async function verifyIdentity() {
    if (!accountId) { connect(); setIdentityError('Connect a NEAR Testnet wallet before signing the ownership challenge.'); return }
    setIdentityState('working')
    setIdentityError(null)
    try {
      const challenge = (await api.creatorChallenge(accountId)).data
      const signed = await signMessage({ message: challenge.message, recipient: challenge.recipient, nonce: decodeBase64(challenge.nonce_b64) })
      if (signed.accountId !== accountId) throw new Error('The wallet signed for a different account.')
      const verified = (await api.creatorVerify({ challenge_id: challenge.challenge_id, account_id: accountId, public_key: signed.publicKey, signature: signed.signature })).data
      const next = { token: verified.session_token, accountId: verified.account_id, expiresAt: verified.session_expires_at }
      localStorage.setItem(SESSION_KEY, JSON.stringify(next))
      setSession(next)
      setIdentityState('verified')
      setNotice(`Wallet ownership verified for ${verified.account_id}.`)
    } catch (error) {
      setIdentityState('error')
      setIdentityError(errorText(error))
    }
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
        <button className="btn creator-verify" onClick={verifyIdentity} disabled={identityState === 'working'}>
          {identityState === 'working' ? 'Waiting for wallet…' : session ? 'Re-verify wallet' : accountId ? 'Verify ownership' : 'Connect wallet'}
        </button>
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
          <div className="creator-side-card creator-limit-card"><span className="creator-label">V1 IDENTITY LIMIT</span><p>Wallet ownership proves control of the signing key at verification time. It does not prove a legal name, editorial quality, or that a human wrote every sentence.</p></div>
        </aside>
      </div>
    </>
  )
}
