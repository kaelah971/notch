import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, ShieldCheck, ShieldQuestion, ExternalLink } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Brief, MarketDetail as MD, MarketEvidence } from '../api/types'
import { cleanQuestion, formatUtc, relativeTo } from '../api/format'
import { PoolBars, StatusBadge, isOpenForEntry, marketCategory, marketTitle, modeLabel, parseRule } from '../components/market'
import { AttentionChart } from '../components/AttentionChart'
import { ParticipationChart } from '../components/ParticipationChart'
import { ShareMarketButton } from '../share/ShareButtons'
import { EntryPanel } from './EntryPanel'
import { ErrorState, SkeletonList } from '../components/States'
import './MarketDetail.css'

type Topic = { article_title: string; source_url?: string }
const short = (h?: string | null) => (h ? `${h.slice(0, 15)}…${h.slice(-6)}` : '—')

export function MarketDetail() {
  const { id = '' } = useParams()
  const [m, reload] = useApi(() => api.market(id).then((r) => r.data), [id])
  const [ev] = useApi(() => api.marketEvidence(id).then((r) => r.data), [id])
  const [br] = useApi(() => api.marketBrief(id).then((r) => r.data.brief), [id])

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
          <BriefPanel brief={br.status === 'ok' ? br.data : null} loading={br.status === 'loading'} errorCode={br.status === 'error' ? br.error.code : null} />
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
              {t.source_url ? <a className="link" href={t.source_url} target="_blank" rel="noreferrer">{t.article_title} <ExternalLink size={13} /></a> : t.article_title}
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
  AI_GENERATED: 'AI-generated · NEAR AI',
  NON_AI_FALLBACK: 'Source-only summary · not AI',
  INVALID_AI_FALLBACK: 'Source-only summary · AI output rejected',
  AI_UNAVAILABLE_FALLBACK: 'Source-only summary · AI unavailable',
}

function BriefPanel({ brief, loading, errorCode }: { brief: Brief | null; loading: boolean; errorCode: string | null }) {
  if (loading) return <div className="card skeleton" style={{ height: 160 }} />
  return (
    <section className="card">
      <div className="card-hrow"><h2 className="card-h">Brief</h2>{brief && <span className="badge">{BRIEF_LABEL[brief.generation_status] ?? brief.generation_status}</span>}</div>
      {!brief ? (
        <p className="dim">{errorCode === 'EVIDENCE_NOT_AVAILABLE' ? 'A brief is published once evidence exists for this market.' : 'No brief is available.'}</p>
      ) : (
        <>
          <p className="brief-head">{brief.headline}</p>
          {typeof brief.summary === 'string' && <p className="brief-sum">{brief.summary}</p>}
          {Array.isArray(brief.observed_signals) && brief.observed_signals.length > 0 && (
            <ul className="brief-list">{(brief.observed_signals as { text: string }[]).map((s, i) => <li key={i}>{s.text}</li>)}</ul>
          )}
          {Array.isArray(brief.uncertainty) && brief.uncertainty.length > 0 && (
            <><h3 className="brief-sub">Uncertainty</h3><ul className="brief-list dim">{(brief.uncertainty as { text: string }[]).map((s, i) => <li key={i}>{s.text}</li>)}</ul></>
          )}
          <p className="fine">The outcome is decided by the frozen rule and evidence, never by this text.</p>
        </>
      )}
    </section>
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
