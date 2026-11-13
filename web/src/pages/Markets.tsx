import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market } from '../api/types'
import { cleanQuestion } from '../api/format'
import { MarketRow, isOpenForEntry, marketTitle, totalPool } from '../components/market'
import { ErrorState, SkeletonList } from '../components/States'
import './Markets.css'

const DAY = 86_400_000
const t = (iso: string) => Date.parse(iso)
const cmpBig = (a: bigint, b: bigint) => (a > b ? -1 : a < b ? 1 : 0)
const isFinal = (m: Market) => ['resolved', 'voided'].includes(m.status)

/**
 * Discovery views. Every rule uses contract fields only. Participant counts aren't exposed by
 * the contract, so stake (test-USDC) is the verified participation signal.
 */
type View = 'all' | 'live' | 'trending' | 'radar' | 'ending' | 'new' | 'resolved'
const VIEWS: { id: View; label: string; rule: string; empty: string; pick: (ms: Market[], now: number) => Market[] }[] = [
  { id: 'all', label: 'All', rule: 'Every onchain market', empty: 'There are no onchain markets yet.',
    pick: (ms) => ms },
  { id: 'live', label: 'Live', rule: 'Open for entries now',
    empty: 'No market is open for entries right now. New markets appear once a rule is approved and created onchain.',
    pick: (ms) => ms.filter(isOpenForEntry) },
  { id: 'trending', label: 'Trending', rule: 'Open markets ranked by total test-USDC staked',
    empty: 'No open market has any stake yet. Trending ranks by verified onchain stake, so it fills as people take positions.',
    pick: (ms) => ms.filter((m) => isOpenForEntry(m) && totalPool(m) > 0n).sort((a, b) => cmpBig(totalPool(a), totalPool(b))) },
  { id: 'radar', label: 'Under the radar', rule: 'Open markets at or below the median stake',
    empty: 'No market is open for entries right now.',
    // Lowest participation first. Says nothing about odds or returns.
    pick: (ms) => {
      const open = ms.filter(isOpenForEntry).sort((a, b) => -cmpBig(totalPool(a), totalPool(b)))
      if (!open.length) return []
      const median = totalPool(open[Math.floor((open.length - 1) / 2)])
      return open.filter((m) => totalPool(m) <= median)
    } },
  { id: 'ending', label: 'Ending soon', rule: 'Entries close within 72 hours',
    empty: 'No open market closes within the next 72 hours.',
    pick: (ms, now) => ms.filter((m) => isOpenForEntry(m) && t(m.close_at_utc) - now < 3 * DAY).sort((a, b) => t(a.close_at_utc) - t(b.close_at_utc)) },
  { id: 'new', label: 'New', rule: 'Created in the last 7 days',
    empty: 'No market was created in the last 7 days.',
    pick: (ms, now) => ms.filter((m) => now - t(m.created_at_utc) < 7 * DAY).sort((a, b) => t(b.created_at_utc) - t(a.created_at_utc)) },
  { id: 'resolved', label: 'Resolved', rule: 'Settled markets and historical demonstrations',
    empty: 'No market has resolved yet.',
    pick: (ms) => ms.filter(isFinal).sort((a, b) => t(b.resolved_at_utc ?? b.close_at_utc) - t(a.resolved_at_utc ?? a.close_at_utc)) },
]

type Kind = 'any' | 'trading' | 'battles'
const KINDS: { id: Kind; label: string }[] = [{ id: 'any', label: 'All types' }, { id: 'trading', label: 'Trend Trading' }, { id: 'battles', label: 'Battles' }]

type Sort = 'default' | 'closing' | 'newest' | 'pool'
const SORTS: { id: Sort; label: string }[] = [
  { id: 'default', label: 'View order' },
  { id: 'closing', label: 'Closing soonest' },
  { id: 'newest', label: 'Newest' },
  { id: 'pool', label: 'Most staked' },
]
const sorters: Record<Exclude<Sort, 'default'>, (a: Market, b: Market) => number> = {
  closing: (a, b) => Number(isOpenForEntry(b)) - Number(isOpenForEntry(a)) || t(a.close_at_utc) - t(b.close_at_utc),
  newest: (a, b) => t(b.created_at_utc) - t(a.created_at_utc),
  pool: (a, b) => cmpBig(totalPool(a), totalPool(b)),
}

export function Markets({ battlesOnly = false }: { battlesOnly?: boolean }) {
  const [state, reload] = useApi(() => api.markets(), [])
  const [params, setParams] = useSearchParams()
  const view: View = (params.get('v') as View) ?? 'all'
  const kind: Kind = battlesOnly ? 'battles' : ((params.get('k') as Kind) ?? 'any')
  const sort: Sort = (params.get('s') as Sort) ?? 'default'
  const [q, setQ] = useState(params.get('q') ?? '')

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v); else next.delete(k)
    setParams(next, { replace: true })
  }

  const now = Date.now()
  const base = useMemo(() => {
    const all = state.status === 'ok' ? state.data.data : []
    const needle = q.trim().toLowerCase()
    return all
      .filter((m) => kind === 'any' || (kind === 'battles' ? m.mode === 'trend_battle' : m.mode === 'trend_trading'))
      .filter((m) => !needle || `${marketTitle(m)} ${cleanQuestion(m.question)} ${m.choices.join(' ')}`.toLowerCase().includes(needle))
  }, [state, kind, q])
  const counts = useMemo(() => Object.fromEntries(VIEWS.map((v) => [v.id, v.pick([...base], now).length])), [base]) // eslint-disable-line react-hooks/exhaustive-deps
  const active = VIEWS.find((v) => v.id === view) ?? VIEWS[0]
  const items = useMemo(() => {
    const list = active.pick([...base], now)
    if (sort !== 'default') list.sort(sorters[sort])
    else if (active.id === 'all') list.sort(sorters.closing)
    return list
  }, [active, base, sort]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <header className="page-head">
        <div>
          <h1>{battlesOnly ? 'Trend Battles' : 'Markets'}</h1>
          <p>{battlesOnly ? 'Two topics. One attention metric. Settled from public evidence.' : 'Call where public attention goes next. Settled from Wikipedia pageviews on NEAR Testnet.'}</p>
          {!battlesOnly && <Link className="btn btn-quiet market-practice-link" to="/app/practice">Try Practice Mode · 1,000 credits</Link>}
        </div>
      </header>

      <nav className="views" aria-label="Discover markets">
        {VIEWS.map((v) => (
          <button key={v.id} className={`view-chip${view === v.id ? ' is-on' : ''}`} aria-pressed={view === v.id} onClick={() => set('v', v.id === 'all' ? null : v.id)}>
            {v.label}{state.status === 'ok' && <span className="view-n">{counts[v.id]}</span>}
          </button>
        ))}
      </nav>

      <div className="mtools">
        <label className="msearch">
          <Search size={18} aria-hidden />
          <input type="search" placeholder="Search markets and topics" value={q} aria-label="Search markets"
            onChange={(e) => { setQ(e.target.value); set('q', e.target.value || null) }} />
        </label>
        {!battlesOnly && (
          <div className="seg" role="group" aria-label="Market type">
            {KINDS.map((k) => <button key={k.id} aria-pressed={kind === k.id} className="seg-btn" onClick={() => set('k', k.id === 'any' ? null : k.id)}>{k.label}</button>)}
          </div>
        )}
        <label className="msort">
          <span className="visually-hidden">Sort</span>
          <select value={sort} onChange={(e) => set('s', e.target.value === 'default' ? null : e.target.value)}>
            {SORTS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </label>
      </div>

      <p className="view-rule">{active.rule}{active.id === 'trending' || active.id === 'radar' ? ' · stake is the onchain participation signal; it is not odds or expected return.' : ''}</p>

      {state.status === 'loading' && <SkeletonList n={2} h={132} />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (items.length
        ? <div className="mgrid">{items.map((m) => <MarketRow key={m.market_id} m={m} />)}</div>
        : <div className="msec-empty"><strong className="txt">Nothing here yet.</strong> {q.trim() ? `No market matches “${q.trim()}” in this view.` : active.empty}</div>)}

      {state.status === 'ok' && !battlesOnly && (
        <p className="fine" style={{ marginTop: 24 }}>“Most active” by number of participants needs an entry log, which the market contract doesn’t expose yet. Views use onchain stake, timing and status only.</p>
      )}
    </>
  )
}
