import { ArrowUpRight, ExternalLink, FileText, ShieldCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { CreatorResearchNote } from '../api/types'
import { useApi } from '../api/useApi'
import { ErrorState, SkeletonList } from '../components/States'
import './CreatorStudio.css'

function NoteCard({ note }: { note: CreatorResearchNote }) {
  return <Link className="creator-public-card" to={`/app/research/notes/${encodeURIComponent(note.note_id)}`}>
    <div className="creator-note-row-top"><span className="creator-label">{note.reference.label}</span><span className="creator-status creator-status-published">PUBLISHED</span></div>
    <h3>{note.title}</h3>
    <p>{note.thesis}</p>
    <div className="creator-public-card-meta"><span>{note.creator_account} · rev {note.revision}</span><span>Inspect <ArrowUpRight size={13} aria-hidden="true" /></span></div>
  </Link>
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
      <aside className="creator-detail-card creator-provenance"><div className="creator-section-head"><div><span className="creator-label">PROVENANCE</span><h2>Inspect the revision</h2></div><FileText size={18} aria-hidden="true" /></div><div className="creator-provenance-row"><span className="creator-label">Content digest</span><strong>{note.content_digest}</strong></div><div className="creator-provenance-row"><span className="creator-label">Evidence digest</span><strong>{note.evidence_digest}</strong></div><div className="creator-provenance-row"><span className="creator-label">Sources</span><strong>{note.source_ids.join(', ')}</strong></div>{note.strategy_reference && <div className="creator-provenance-row"><span className="creator-label">Strategy reference · as supplied</span><strong>{note.strategy_reference.id} / {note.strategy_reference.revision_hash}</strong></div>}<div><span className="creator-label">Revision history</span><div className="creator-revision-list">{(note.revision_history ?? []).map((revision) => <div className="creator-revision" key={revision.revision}><span>rev {revision.revision} · {revision.status}</span><span>{revision.content_digest.slice(0, 16)}…</span></div>)}</div></div><p className="creator-muted">Publication proves a signed account controlled the publishing key. It does not turn interpretation into fact or attest to an author’s legal identity.</p></aside>
    </div>
  </div>
}
