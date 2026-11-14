import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, ShieldCheck, ShieldQuestion, ExternalLink } from 'lucide-react'
import { ApiError, api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Brief, BriefClaim, BriefEvidenceReference, MarketDetail as MD, MarketEvidence, ResearchCouncil, CouncilRole, CouncilClaim } from '../api/types'
import { cleanQuestion, formatUtc, relativeTo } from '../api/format'
import { PoolBars, StatusBadge, isOpenForEntry, marketCategory, marketTitle, modeLabel, parseRule } from '../components/market'
import { AttentionChart } from '../components/AttentionChart'
import { ParticipationChart } from '../components/ParticipationChart'
import { ShareMarketButton } from '../share/ShareButtons'
import { EntryPanel } from './EntryPanel'
import { ErrorState, SkeletonList } from '../components/States'
import './MarketDetail.css'

type Topic = { article_title: string; source_url?: string }
type ResearchState =
  | { marketId: string; status: 'idle' }
  | { marketId: string; status: 'loading' }
  | { marketId: string; status: 'ok'; brief: Brief }
  | { marketId: string; status: 'error'; error: ApiError }
type CouncilState =
  | { marketId: string; status: 'idle' }
  | { marketId: string; status: 'loading' }
  | { marketId: string; status: 'ok'; council: ResearchCouncil }
  | { marketId: string; status: 'error'; error: ApiError }
const short = (h?: string | null) => (h ? `${h.slice(0, 15)}…${h.slice(-6)}` : '—')

export function MarketDetail() {
  const { id = '' } = useParams()
  const [m, reload] = useApi(() => api.market(id).then((r) => r.data), [id])
  const [ev] = useApi(() => api.marketEvidence(id).then((r) => r.data), [id])
  const [br] = useApi(() => api.marketBrief(id).then((r) => r.data.brief), [id])
  const [research, setResearch] = useState<ResearchState>({ marketId: id, status: 'idle' })
  const [council, setCouncil] = useState<CouncilState>({ marketId: id, status: 'idle' })

  const requestResearch = () => {
    setResearch({ marketId: id, status: 'loading' })
    api.marketResearch(id).then(
      (response) => setResearch({ marketId: id, status: 'ok', brief: response.data.brief }),
      (error) => setResearch({ marketId: id, status: 'error', error: error instanceof ApiError ? error : new ApiError(0, 'UNKNOWN', String(error)) }),
    )
  }
  const requestCouncil = () => {
    setCouncil({ marketId: id, status: 'loading' })
    api.marketCouncil(id).then(
      (response) => setCouncil({ marketId: id, status: 'ok', council: response.data.council }),
      (error) => setCouncil({ marketId: id, status: 'error', error: error instanceof ApiError ? error : new ApiError(0, 'UNKNOWN', String(error)) }),
    )
  }
  const researchForMarket = research.marketId === id ? research : { marketId: id, status: 'idle' as const }
  const councilForMarket = council.marketId === id ? council : { marketId: id, status: 'idle' as const }

  // Open markets: silently re-read pools from the contract every 20s (no skeleton flash).
  const [fresh, setFresh] = useState<{ d: MD; at: number } | null>(null)
  const open = m.status === 'ok' && isOpenForEntry(m.data)
  useEffect(() => {
    setFresh(null)
    if (!open) return
    const h = window.setInterval(() => { if (!document.hidden) api.market(id).then((r) => setFresh({ d: r.data, at: Date.now() }), () => {}) }, 20_000)
    return () => clearInterval(h)
  }, [id, open])

  if (m.status === 'loading') return <SkeletonList n={2} h={220} />
  if (m.status === 'error') return <ErrorState error={m.error} onRetry={reload} />
  const d = fresh?.d ?? m.data

  return (
    <article className="md">
      <Link to="/app/markets" className="md-back"><ChevronLeft size={18} /> Markets</Link>

      <header className="md-head">
        <div className="md-tags"><span className="mrow-mode">{modeLabel(d)} · {marketCategory(d)}</span><StatusBadge m={d} /></div>
        <div className="md-titlerow"><h1>{marketTitle(d)}</h1><ShareMarketButton m={d} /></div>
        <p className="md-q">{cleanQuestion(d.question)}</p>
        {d.is_historical_replay && (
          <p className="md-note" role="note">
            This is a resolved historical demonstration. Its window had already happened when it was created, so it is not a prediction and does not count toward performance.
          </p>
        )}
      </header>

      <div className="md-grid">
        <div className="md-main">
          <AttentionCard d={d} />
          <section className="card">
            <h2 className="card-h">Stake distribution</h2>
            <PoolBars m={d} />
            <div style={{ marginTop: 20 }}><ParticipationChart m={d} /></div>
            <p className="fine">Read from the market contract{open ? ` · refreshes every 20s${fresh ? `, last ${new Date(fresh.at).toLocaleTimeString()}` : ''}` : ''}. Pooled market: winners share the whole pool pro rata. The split shows stakes, not odds or probabilities.</p>
          </section>
          <Measurement d={d} />
          <Timeline d={d} />
          <RulePanel d={d} />
          <EvidencePanel ev={ev.status === 'ok' ? ev.data : null} loading={ev.status === 'loading'} onchainHash={d.evidence_hash} />
          <section className="card">
            <h2 className="card-h">Activity</h2>
            <p className="dim">Per-entry history isn’t available yet: the contract exposes pool totals and per-account positions, not an entry log or participant count. Indexing the market’s <span className="mono">ft_on_transfer</span> receipts would add it without contract changes.</p>
          </section>
          <ResearchPanel marketId={id} fallbackBrief={br.status === 'ok' ? br.data : null} research={researchForMarket} onRequest={requestResearch} />
          <ResearchCouncilPanel council={councilForMarket} onRequest={requestCouncil} />
        </div>
        <aside className="md-side">
          <EntryPanel d={d} onPositionChange={reload} />
          <Link className="practice-market-cta" to={`/app/practice?market=${encodeURIComponent(d.market_id)}`}>
            <span><strong>Practice Mode</strong><small>Try this question with 1,000 virtual credits. No wallet or test-USDC.</small></span>
            <span aria-hidden="true">→</span>
          </Link>
        </aside>
      </div>
    </article>
  )
}

function Timeline({ d }: { d: MD }) {
  const rows: [string, string | null][] = [
    ['Opened', d.open_at_utc], ['Entries close', d.close_at_utc], ['Resolution eligible', d.resolve_after_utc], ['Resolved', d.resolved_at_utc],
  ]
  return (
    <section className="card">
      <h2 className="card-h">Timeline</h2>
      <dl className="kv">
        {rows.filter(([, v]) => v).map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd><time dateTime={v!}>{formatUtc(v!)}</time> <span className="dim">· {relativeTo(v!)}</span></dd></div>
        ))}
      </dl>
    </section>
  )
}

function RulePanel({ d }: { d: MD }) {
  const rule = d.rule as Record<string, unknown> | null | undefined
  const topics = (rule?.topics as Topic[] | undefined) ?? []
  const rec = d.rule_record as { status?: string; approved_by?: string; approved_at?: string } | null | undefined
  return (
    <section className="card">
      <h2 className="card-h">Locked market rule</h2>
      {!rule ? <p className="dim">No canonical rule is stored for this market.</p> : (
        <dl className="kv">
          <div><dt>Source</dt><dd>Wikimedia Pageviews <span className="dim">({d.source_id})</span></dd></div>
          {topics.map((t) => (
            <div key={t.article_title}><dt>Topic</dt><dd>
              {t.source_url ? <a className="link" href={t.source_url} target="_blank" rel="noreferrer">{t.article_title} <ExternalLink aria-hidden="true" size={13} /></a> : t.article_title}
            </dd></div>
          ))}
          <div><dt>If data is missing</dt><dd>{String(rule.missing_data_policy ?? '—')}</dd></div>
          <div><dt>If invalid</dt><dd>{String(rule.invalidation_policy ?? '—')}</dd></div>
          {rec?.status && <div><dt>Approval</dt><dd>{rec.status} by {rec.approved_by}{rec.approved_at ? ` · ${formatUtc(rec.approved_at)}` : ''}</dd></div>}
          <div><dt>Onchain rule hash</dt><dd className="mono hash" title={d.rule_hash}>{short(d.rule_hash)}</dd></div>
        </dl>
      )}
    </section>
  )
}

function EvidencePanel({ ev, loading, onchainHash }: { ev: MarketEvidence | null; loading: boolean; onchainHash: string | null }) {
  if (loading) return <div className="card skeleton" style={{ height: 120 }} />
  const verified = ev?.verified === true
  const digest = (ev?.evidence_digest as string | null | undefined) ?? null
  return (
    <section className="card">
      <h2 className="card-h">Evidence</h2>
      {!ev?.evidence_available ? (
        <p className="ev-row"><ShieldQuestion size={18} /> Evidence is not available yet. It is collected after the observation window closes.</p>
      ) : (
        <>
          <p className={`ev-row${verified ? ' is-ok' : ''}`}>
            {verified ? <ShieldCheck size={18} /> : <ShieldQuestion size={18} />}
            {verified ? 'Evidence verified against the frozen rule.' : 'Evidence present but not verified.'}
          </p>
          <dl className="kv">
            <div><dt>Evidence digest</dt><dd className="mono hash" title={digest ?? ''}>{short(digest)}</dd></div>
            <div><dt>Onchain evidence hash</dt><dd className="mono hash" title={onchainHash ?? ''}>{short(onchainHash)}{digest && onchainHash && <span className={digest === onchainHash ? 'ok' : 'bad'}> {digest === onchainHash ? '· matches' : '· mismatch'}</span>}</dd></div>
          </dl>
        </>
      )}
    </section>
  )
}

const BRIEF_LABEL: Record<string, string> = {
  LIVE_AI_VERIFIED: 'LIVE_AI_VERIFIED · locally validated',
  DETERMINISTIC_FALLBACK: 'DETERMINISTIC_FALLBACK',
  UNAVAILABLE: 'UNAVAILABLE',
  AI_GENERATED: 'LIVE_AI_VERIFIED · locally validated',
  NON_AI_FALLBACK: 'DETERMINISTIC_FALLBACK',
  INVALID_AI_FALLBACK: 'DETERMINISTIC_FALLBACK · AI rejected',
  AI_UNAVAILABLE_FALLBACK: 'DETERMINISTIC_FALLBACK · AI unavailable',
}

function ResearchPanel({ marketId, fallbackBrief, research, onRequest }: { marketId: string; fallbackBrief: Brief | null; research: ResearchState; onRequest: () => void }) {
  const navigate = useNavigate()
  const brief = research.status === 'ok' ? research.brief : fallbackBrief
  const inference = brief?.inference
  const inferenceStatus = inference?.status ?? brief?.generation_status ?? 'UNAVAILABLE'
  const verification = inference?.verification
  const verified = verification?.status === 'verified'
  const inputDigest = inference?.input_digest ?? (typeof brief?.input_digest === 'string' ? brief.input_digest : undefined)
  const errorText = research.status === 'error'
    ? research.error.code === 'RATE_LIMITED' || research.error.code === 'NEAR_AI_RATE_LIMITED' ? 'NEAR AI is rate limited. Wait briefly, then try again.'
      : research.error.code === 'NETWORK' ? 'The research API is unreachable. Your market and wallet state are unchanged.'
        : research.error.code === 'RULE_NOT_AVAILABLE' ? 'This market has no published rule available for research.'
          : 'Research is unavailable right now. The market remains usable without AI.'
    : null
  return (
    <section className="card md-research" aria-labelledby="market-research-title">
      <div className="card-hrow"><h2 className="card-h" id="market-research-title">AI market research</h2><span className="badge">{BRIEF_LABEL[inferenceStatus] ?? inferenceStatus}</span></div>
      <p className="md-research-intro">Request a bounded brief grounded in this market’s published rule, available Wikimedia observations, and matching historical context. AI interpretation is separate from verified source data and never places a prediction. This is read-only: no wallet, signature, or transaction is requested.</p>
      <div className="creator-actions">
        <button type="button" className="btn btn-primary md-research-trigger" onClick={onRequest} disabled={research.status === 'loading'} aria-busy={research.status === 'loading'}>
          {research.status === 'loading' ? 'Inspecting evidence…' : 'Request research brief'}
        </button>
        {brief && <button type="button" className="btn btn-quiet" onClick={() => navigate('/app/vault', { state: { marketId, title: brief.headline, thesis: brief.summary ?? '', sourceReferences: brief.evidence_references.flatMap((reference) => [reference.ref_id, reference.url ?? '']).filter(Boolean) } })}>Save privately</button>}
      </div>
      {research.status === 'loading' && <p className="md-research-status" role="status">Reading the published rule and source observations. No wallet or signing call is made.</p>}
      {errorText && <div className="md-research-error" role="alert"><strong>{errorText}</strong><button type="button" className="btn btn-quiet" onClick={onRequest}>Try again</button></div>}
      {!brief && research.status !== 'loading' && !errorText && <p className="dim md-research-empty">No source-only brief is available yet. Request research to inspect this market’s evidence package.</p>}
      {brief && (
        <>
          <div className="md-research-boundary"><strong>Interpretation boundary</strong><span>The published rule and source observations are supplied with timestamps, hashes and source links. Finalized oracle evidence is marked verified separately. The sections below are AI commentary or deterministic fallback text; no calibrated probability is shown.</span></div>
          <p className="brief-head">{brief.headline}</p>
          {brief.summary && <p className="brief-sum">{brief.summary}</p>}
          {brief.fallback_reason && <p className="fine">Source-only status: {brief.fallback_reason}</p>}
          {brief.resolution && <div className="md-research-rule"><h3>Published resolution criteria</h3><p>{typeof brief.resolution.text === 'string' ? brief.resolution.text : 'The published rule is available above.'}</p>{typeof brief.resolution.formula === 'string' && <code>{brief.resolution.formula}</code>}</div>}
          <ResearchClaimSection title="Evidence supporting UP" claims={brief.research?.supporting_up ?? []} tone="up" />
          <ResearchClaimSection title="Evidence supporting DOWN" claims={brief.research?.supporting_down ?? []} tone="down" />
          <ResearchClaimSection title="Key assumptions" claims={brief.research?.key_assumptions ?? []} />
          <ResearchClaimSection title="Historical context" claims={brief.research?.historical_context ?? []} />
          <ResearchClaimSection title="Uncertainty" claims={brief.uncertainty ?? []} muted />
          {!!brief.missing_evidence?.length && <ResearchTextList title="Missing information" items={brief.missing_evidence} />}
          {!!brief.suggested_research_questions?.length && <ResearchTextList title="Investigate next" items={brief.suggested_research_questions} />}
          <ResearchSources references={brief.evidence_references ?? []} />
          <div className="md-research-meta">
            <span>Provider: <strong>{inference?.provider ?? brief.provider}</strong> · model: <strong>{inference?.model ?? brief.model}</strong></span>
            <span>Observation as-of: <strong>{inference?.input_observation_cutoff ?? String(brief.measurement_window?.observation_cutoff ?? brief.data_as_of ?? 'unavailable')}</strong></span>
            <span>Input package digest: <code>{short(inputDigest)}</code></span>
            {inference?.input_evidence_digest && <span>Oracle evidence digest: <code>{short(inference.input_evidence_digest)}</code></span>}
            <span className={verified ? 'md-research-verified' : 'md-research-unverified'}>{verified ? 'Verified Inference' : 'Inference verification unavailable'}{verification?.reason ? ` · ${verification.reason}` : ''}</span>
          </div>
        </>
      )}
    </section>
  )
}

const COUNCIL_STATUS_LABEL: Record<string, string> = {
  LIVE_AI_VERIFIED: 'LIVE_AI_VERIFIED · shared response validated',
  DETERMINISTIC_FALLBACK: 'DETERMINISTIC_FALLBACK',
  UNAVAILABLE: 'UNAVAILABLE',
  AI_GENERATED: 'LIVE_AI_VERIFIED · shared response validated',
  NON_AI_FALLBACK: 'DETERMINISTIC_FALLBACK',
  AI_UNAVAILABLE_FALLBACK: 'DETERMINISTIC_FALLBACK · AI unavailable',
  INVALID_AI_FALLBACK: 'DETERMINISTIC_FALLBACK · AI rejected',
  MIXED_AI_AND_FALLBACK: 'DETERMINISTIC_FALLBACK · mixed roles',
  DETERMINISTIC_EVIDENCE_LENSES: 'DETERMINISTIC_FALLBACK',
}

function ResearchCouncilPanel({ council, onRequest }: { council: CouncilState; onRequest: () => void }) {
  const record = council.status === 'ok' ? council.council : null
  const councilStatus = record?.inference_status ?? (record ? record.generation_mode : 'UNAVAILABLE')
  const errorText = council.status === 'error'
    ? council.error.code === 'NETWORK' ? 'The research API is unreachable. Market and wallet state are unchanged.'
      : council.error.code === 'RULE_NOT_AVAILABLE' ? 'This market has no published rule available for the council.'
        : 'The council is unavailable right now. No wallet or signing action was requested.'
    : null
  return (
    <section className="card md-council" aria-labelledby="research-council-title">
      <div className="card-hrow">
        <div>
          <h2 className="card-h" id="research-council-title">Research council</h2>
          <p className="md-council-kicker">Three lenses · one bounded evidence snapshot</p>
        </div>
        <span className="badge">{COUNCIL_STATUS_LABEL[councilStatus] ?? councilStatus}</span>
      </div>
      <p className="md-research-intro">Ask Bull Analyst, Bear Analyst, and Evidence Verifier to inspect the same published rule, Wikimedia observations, and matching historical context. Claims stay cited and descriptive: no probability, trade, wallet, or settlement action is created.</p>
      <button type="button" className="btn btn-primary md-research-trigger" onClick={onRequest} disabled={council.status === 'loading'} aria-busy={council.status === 'loading'}>
        {council.status === 'loading' ? 'Convening council…' : 'Open research council'}
      </button>
      {council.status === 'loading' && <p className="md-research-status" role="status">Freezing one evidence snapshot and checking three read-only lenses. No wallet or signing call is made.</p>}
      {errorText && <div className="md-research-error" role="alert"><strong>{errorText}</strong><button type="button" className="btn btn-quiet" onClick={onRequest}>Try again</button></div>}
      {record && (
        <>
          <div className="md-council-boundary"><strong>Shared snapshot</strong><span><code>{record.snapshot.snapshot_id}</code> · source package <code>{short(record.snapshot.snapshot_digest)}</code> · as of <strong>{record.snapshot.data_as_of || 'unavailable'}</strong></span></div>
          {record.inference?.role_generation === 'one_shared_model_response' && <p className="fine">One NEAR AI response was locally validated into all three lenses; Bull, Bear, and Verifier are not independent model calls.</p>}
          <div className="md-council-roles">
            {record.roles.map((role) => <CouncilRoleCard key={role.role_id} role={role} />)}
          </div>
          <div className="md-council-disagreement">
            <div className="md-council-section-head"><h3>Disagreement tracking</h3><span className={`badge council-${record.disagreement.status.toLowerCase()}`}>{record.disagreement.status.replace(/_/g, ' ')}</span></div>
            <p>{record.disagreement.summary}</p>
            {record.disagreement.records.map((item, index) => <div className="md-council-record" key={`${String(item.kind ?? 'record')}-${index}`}><span>Bull refs</span><code>{refsFromRecord(item, 'bull_evidence_refs')}</code><span>Bear refs</span><code>{refsFromRecord(item, 'bear_evidence_refs')}</code></div>)}
          </div>
          <div className="md-council-audit">
            <span>Audit <code>{record.audit.audit_id}</code></span>
            <span>Input <code>{short(record.snapshot.input_digest)}</code></span>
            <span>Result <code>{short(record.result_digest)}</code></span>
            <span className="md-council-safe">Read-only boundary · no broadcast, publication, or settlement</span>
          </div>
        </>
      )}
      {!record && council.status !== 'loading' && !errorText && <p className="dim md-research-empty">No council record has been generated for this market yet.</p>}
    </section>
  )
}

function CouncilRoleCard({ role }: { role: CouncilRole }) {
  const tone = role.role_id === 'bull_analyst' ? 'bull' : role.role_id === 'bear_analyst' ? 'bear' : 'verify'
  return (
    <article className={`md-council-role is-${tone}`}>
      <div className="md-council-role-head"><div><span className="md-council-role-label">{role.label}</span><h3>{role.headline}</h3></div><span className="md-council-stance">{role.position}</span></div>
      <p className="md-council-thesis">{role.thesis}</p>
      <ResearchClaimSection title="Cited claims" claims={role.claims} tone={tone === 'bull' ? 'up' : tone === 'bear' ? 'down' : undefined} />
      <ResearchClaimSection title="Counterpoints" claims={role.counterpoints} muted />
      <ResearchTextList title="Open questions" items={role.open_questions} />
      <div className="md-council-role-meta"><span>{COUNCIL_STATUS_LABEL[role.generation_status] ?? role.generation_status}</span><span className={role.citation_validation.status === 'valid' ? 'md-council-cited' : 'bad'}>{role.citation_validation.status === 'valid' ? 'Citations checked' : 'Citation issue'}</span></div>
      {role.fallback_reason && <p className="fine">{role.fallback_reason}</p>}
    </article>
  )
}

function refsFromRecord(record: Record<string, unknown>, key: string) {
  const refs = record[key]
  return Array.isArray(refs) && refs.length ? refs.join(' · ') : 'none'
}

function ResearchClaimSection({ title, claims, tone, muted = false }: { title: string; claims: Array<BriefClaim | CouncilClaim>; tone?: 'up' | 'down'; muted?: boolean }) {
  return (
    <div className={`md-research-section${tone ? ` is-${tone}` : ''}${muted ? ' is-muted' : ''}`}>
      <h3>{title}</h3>
      {!claims.length ? <p className="dim">No supplied claim in this section.</p> : <ul className="md-research-claims">{claims.map((claim) => <li key={`${claim.kind}:${claim.text}`}><div className="md-claim-head"><span className="md-claim-kind">{claim.kind}</span>{claim.evidence_refs.length > 0 && <span className="md-claim-refs">{claim.evidence_refs.join(' · ')}</span>}</div><p>{claim.text}</p></li>)}</ul>}
    </div>
  )
}

function ResearchTextList({ title, items }: { title: string; items: string[] }) {
  return <div className="md-research-section is-muted"><h3>{title}</h3><ul className="md-research-claims">{items.map((item) => <li key={item}><p>{item}</p></li>)}</ul></div>
}

function ResearchSources({ references }: { references: BriefEvidenceReference[] }) {
  return (
    <div className="md-research-sources">
      <h3>Source references</h3>
      {!references.length ? <p className="dim">No source references were supplied.</p> : <ul>{references.map((reference) => <li key={reference.ref_id}><code>{reference.ref_id}</code><span>{reference.title} · {reference.source}{reference.observed_at ? ` · ${reference.observed_at}` : ''}</span>{reference.url && <a className="link" href={reference.url} target="_blank" rel="noreferrer">Open source <ExternalLink aria-hidden="true" size={12} /></a>}</li>)}</ul>}
    </div>
  )
}

function articlesFor(d: MD): { article: string; label: string }[] {
  if (d.battle) return [d.battle.topic_a, d.battle.topic_b].map((t) => ({ article: t.article_title.replace(/ /g, '_'), label: t.article_title }))
  const src = (d.rule as { source?: { article?: string } } | null | undefined)?.source?.article
  const r = parseRule(d)
  const article = src ?? r?.topic?.replace(/ /g, '_')
  return article ? [{ article, label: article.replace(/_/g, ' ') }] : []
}

function AttentionCard({ d }: { d: MD }) {
  const arts = articlesFor(d)
  const r = parseRule(d)
  if (!arts.length) return null
  return (
    <section className="card">
      <h2 className="card-h">Attention index</h2>
      <AttentionChart articles={arts}
        markers={r ? [{ date: r.baseline, label: 'baseline' }, { date: r.target, label: 'target' }] : []}
        baselineDate={r?.baseline} thresholdPct={d.battle ? undefined : r?.thresholdPct} />
    </section>
  )
}

/** Exact metric, days and decision rule, all from the locked onchain question. */
function Measurement({ d }: { d: MD }) {
  const r = parseRule(d)
  if (!r) return null
  const arts = articlesFor(d)
  return (
    <section className="card">
      <h2 className="card-h">What’s measured</h2>
      <dl className="kv">
        <div><dt>Metric</dt><dd>Daily pageviews · en.wikipedia.org · all-access · user agents · UTC</dd></div>
        <div><dt>Article{arts.length > 1 ? 's' : ''}</dt><dd>{arts.map((a) => a.label).join(' vs ')}</dd></div>
        <div><dt>Baseline day</dt><dd>{r.baseline} (full UTC day)</dd></div>
        <div><dt>Target day</dt><dd>{r.target} (full UTC day)</dd></div>
        <div><dt>Resolves</dt><dd>{d.battle
          ? `${d.choices[0]} or ${d.choices[1]} — whichever has higher normalized growth. Within ${(d.battle.tie_tolerance_bps / 100).toFixed(2)}% is a tie and the market is voided (stakes refunded).`
          : `UP if target-day views ≥ baseline-day views × ${(1 + Number(r.thresholdPct) / 100).toFixed(4)} (growth ≥ ${r.thresholdPct}%); otherwise DOWN.`}</dd></div>
      </dl>
    </section>
  )
}
