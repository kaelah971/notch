import { useState } from 'react'
import { ArrowUpRight, ChevronDown, ExternalLink, FileSearch } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AttentionChart } from '../components/AttentionChart'
import { ErrorState, SkeletonList } from '../components/States'
import { api } from '../api/client'
import type { ScoutCandidate, ScoutDirection } from '../api/types'
import { useApi } from '../api/useApi'
import { Pulse } from '../pulse/Pulse'
import './Discover.css'

const nf = new Intl.NumberFormat('en-US')
const directionLabels: { value: ScoutDirection; label: string }[] = [
  { value: 'all', label: 'All movements' },
  { value: 'rising', label: 'Rising' },
  { value: 'falling', label: 'Falling' },
]

function changeLabel(item: ScoutCandidate) {
  const value = item.change.change_percent
  if (value == null) return 'Unavailable'
  return `${value >= 0 ? '+' : ''}${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}%`
}

function statusLabel(item: ScoutCandidate) {
  if (item.existing_market_match) return 'Published market'
  if (item.proposal) return 'Research candidate'
  if (item.candidate_status === 'STALE') return 'Stale evidence'
  if (item.candidate_status === 'NEEDS_REVIEW') return 'Needs review'
  return 'Observed movement'
}

function freshnessLabel(item: ScoutCandidate) {
  const age = item.freshness.age_hours
  if (age == null) return 'Freshness unavailable'
  if (age < 1) return 'Observed less than an hour ago'
  if (age < 24) return `Observed ${Math.round(age)}h ago`
  return `Observed ${Math.round(age / 24)}d ago`
}

function EvidencePanel({ item }: { item: ScoutCandidate }) {
  return (
    <div className="scout-evidence">
      <div className="scout-evidence-grid">
        <div>
          <span className="scout-label">Observation window</span>
          <strong>{item.observation_window.start ?? '—'} → {item.observation_window.end ?? '—'}</strong>
          <span className="scout-muted">{item.observation_window.sample_count}/{item.observation_window.expected_days} daily observations</span>
        </div>
        <div>
          <span className="scout-label">Evidence digest</span>
          <strong className="mono scout-digest">{item.evidence_digest}</strong>
          <span className="scout-muted">Raw source hashes: {item.evidence.raw_hashes.length || 'none recorded'}</span>
        </div>
      </div>
      <AttentionChart articles={[{ article: item.source_article, label: item.topic }]} defaultRange={30} />
      <div className="scout-source-row">
        <a href={item.source_url} target="_blank" rel="noreferrer">
          Wikimedia article <ExternalLink size={14} aria-hidden="true" />
        </a>
        {item.source.api_url && <a href={item.source.api_url} target="_blank" rel="noreferrer">Pageviews API <ExternalLink size={14} aria-hidden="true" /></a>}
      </div>
      {(item.uncertainty.length > 0 || item.limitations.length > 0) && (
        <div className="scout-notes">
          <span className="scout-label">Uncertainty and limits</span>
          <ul>
            {[...item.uncertainty, ...item.limitations].map((note) => <li key={note}>{note}</li>)}
          </ul>
        </div>
      )}
      <div className="scout-observations" aria-label={`${item.topic} daily observations`}>
        {item.evidence.daily.map((row) => (
          <span key={row.observation_id} className="scout-observation mono">
            <time dateTime={row.date}>{row.date}</time> <b>{nf.format(row.views)}</b>
          </span>
        ))}
      </div>
    </div>
  )
}

function ScoutCard({ item, rank, open, onToggle }: { item: ScoutCandidate; rank: number; open: boolean; onToggle: () => void }) {
  const directionClass = item.direction.toLowerCase()
  return (
    <article className={`scout-card is-${directionClass}`}>
      <div className="scout-card-main">
        <div className="scout-rank mono">{String(rank).padStart(2, '0')}</div>
        <div className="scout-card-copy">
          <div className="scout-title-row">
            <h2>{item.topic}</h2>
            <span className={`scout-direction scout-direction-${directionClass}`}>{item.direction}</span>
            {item.is_unusual && <span className="scout-unusual">Unusual</span>}
          </div>
          <p className="scout-meta">{statusLabel(item)} · {freshnessLabel(item)} · {item.observation_window.sample_count} days</p>
          <div className="scout-measures">
            <div><span className="scout-label">Baseline</span><strong className="num">{item.baseline ? nf.format(item.baseline.views) : '—'}</strong><span>{item.baseline?.date ?? 'Unavailable'}</span></div>
            <div><span className="scout-label">Current</span><strong className="num">{item.current ? nf.format(item.current.views) : '—'}</strong><span>{item.current?.date ?? 'Unavailable'}</span></div>
            <div className="scout-change"><span className="scout-label">Change</span><strong className="num">{changeLabel(item)}</strong><span>{item.change.change_bps == null ? 'zero baseline / missing' : `${item.change.change_bps.toLocaleString('en-US')} bps`}</span></div>
          </div>
        </div>
        <div className="scout-card-actions">
          <span className="scout-score mono" aria-label={`Scout rank score ${item.rank.score}`}>{item.rank.score}</span>
          <button className="scout-expand" aria-expanded={open} aria-controls={`scout-evidence-${item.candidate_id}`} aria-label={`${open ? 'Hide' : 'Show'} ${item.topic} evidence`} onClick={onToggle}>
            <ChevronDown size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="scout-card-footer">
        <span className="scout-source-tag"><span className="scout-dot" aria-hidden="true" />Observed Wikimedia attention</span>
        {item.existing_market_match ? (
          <Link className="scout-action" to={`/app/markets/${encodeURIComponent(item.existing_market_match.market_id)}`}>
            Open market research <ArrowUpRight size={14} aria-hidden="true" />
          </Link>
        ) : item.proposal ? (
          <div className="scout-card-footer-actions">
            <span className="scout-review"><FileSearch size={14} aria-hidden="true" /> Review-only proposal</span>
            <Link className="scout-action" to={`/app/strategy-builder?candidate=${encodeURIComponent(item.candidate_id)}`}>
              Build strategy <ArrowUpRight size={14} aria-hidden="true" />
            </Link>
          </div>
        ) : (
          <span className="scout-review">No proposal: evidence is not yet suitable</span>
        )}
      </div>
      {open && <div id={`scout-evidence-${item.candidate_id}`}><EvidencePanel item={item} /></div>}
    </article>
  )
}

export function Discover() {
  const [direction, setDirection] = useState<ScoutDirection>('all')
  const [open, setOpen] = useState<string | null>(null)
  const [state, reload] = useApi(() => api.scout(direction), [direction])
  const [marketsState] = useApi(() => api.markets(), [])

  return (
    <>
      <header className="page-head scout-head">
        <div>
          <p className="eyebrow">WIKIMEDIA ATTENTION / SCOUT V1</p>
          <h1>Discover</h1>
          <p>Find unusual, source-backed attention movements before deciding whether they deserve a forecast.</p>
        </div>
        <div className="scout-method-note"><span className="scout-dot" aria-hidden="true" />Deterministic · no AI required</div>
      </header>

      <div className="scout-toolbar">
        <div className="seg" role="group" aria-label="Attention movement direction">
          {directionLabels.map((item) => (
            <button key={item.value} className="seg-btn" aria-pressed={direction === item.value} onClick={() => { setDirection(item.value); setOpen(null) }}>
              {item.label}
            </button>
          ))}
        </div>
        <p className="scout-formula mono">change_bps = floor((current − baseline) × 10000 / baseline)</p>
      </div>

      {state.status === 'loading' && <SkeletonList n={4} h={150} />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (
        state.data.data.length === 0 ? (
          <div className="state scout-empty"><h2>No supported movement yet</h2><p>{state.data.meta?.reason ?? 'The stored Radar observations do not currently contain a fresh, reviewable movement for the supported Scout topics.'}</p><button className="btn" onClick={reload}>Check again</button></div>
        ) : (
          <>
            <div className="scout-summary"><strong>{state.data.data.length} movement{state.data.data.length === 1 ? '' : 's'}</strong><span>from {state.data.meta?.source ?? 'stored Wikimedia observations'}</span></div>
            <section className="scout-list" aria-label="Emerging attention candidates">
              {state.data.data.map((item, index) => <ScoutCard key={item.candidate_id} item={item} rank={index + 1} open={open === item.candidate_id} onToggle={() => setOpen(open === item.candidate_id ? null : item.candidate_id)} />)}
            </section>
          </>
        )
      )}
      <Pulse markets={marketsState.status === 'ok' ? marketsState.data.data : []} />
    </>
  )
}
