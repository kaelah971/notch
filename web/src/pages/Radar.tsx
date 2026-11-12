import { ExternalLink } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import { relativeTo } from '../api/format'
import { ErrorState, SkeletonList } from '../components/States'
import './Radar.css'

export function Radar() {
  const [state, reload] = useApi(() => api.trends(), [])
  return (
    <>
      <header className="page-head">
        <div><h1>Trend Radar</h1><p>Topics with measurable public attention, ranked by the stored Radar score.</p></div>
      </header>
      {state.status === 'loading' && <SkeletonList n={6} h={64} />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (state.data.data.length === 0
        ? <div className="state"><h2>No eligible trends</h2><p>The Radar has no eligible candidates right now.</p></div>
        : (
          <ol className="rlist">
            {state.data.data.map((t, i) => (
              <li key={t.candidate_id} className="rrow">
                <span className="rrank mono">{i + 1}</span>
                <div className="rmain">
                  <p className="rtitle">{t.title}</p>
                  <p className="rmeta">{t.category} · {t.sources.join(', ')} · observed {relativeTo(t.observed_at)}</p>
                </div>
                {t.settlement_coverage && (
                  <span className="rviews mono" title={`Wikimedia views on ${t.settlement_coverage.latest_date}`}>
                    {t.settlement_coverage.latest_views.toLocaleString('en-US')} <span className="dim">views</span>
                  </span>
                )}
                <span className="rscore mono" aria-label={`Radar score ${t.score}`}>{t.score}</span>
                {t.source_urls[0] && <a className="rlink" href={t.source_urls[0]} target="_blank" rel="noreferrer" aria-label={`Source for ${t.title}`}><ExternalLink size={16} /></a>}
              </li>
            ))}
          </ol>
        ))}
    </>
  )
}
