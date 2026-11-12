import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market } from '../api/types'
import { MarketRow, isOpenForEntry } from '../components/market'
import { ErrorState, SkeletonList } from '../components/States'
import './Markets.css'

type Filter = 'all' | 'open' | 'trading' | 'battles' | 'resolved'
const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'open', label: 'Open' },
  { id: 'trading', label: 'Trend Trading' },
  { id: 'battles', label: 'Battles' },
  { id: 'resolved', label: 'Resolved demos' },
]

const match: Record<Filter, (m: Market) => boolean> = {
  all: () => true,
  open: isOpenForEntry,
  trading: (m) => m.mode === 'trend_trading',
  battles: (m) => m.mode === 'trend_battle',
  resolved: (m) => m.is_historical_replay,
}

export function Markets({ battlesOnly = false }: { battlesOnly?: boolean }) {
  const [state, reload] = useApi(() => api.markets(), [])
  const [params, setParams] = useSearchParams()
  const filter: Filter = battlesOnly ? 'battles' : ((params.get('f') as Filter) ?? 'all')

  const { open, battles, rest } = useMemo(() => {
    const all = state.status === 'ok' ? state.data.data : []
    const shown = all.filter(match[filter] ?? match.all)
    // Open future predictions always lead; historical demos follow.
    shown.sort((a, b) => Number(isOpenForEntry(b)) - Number(isOpenForEntry(a)))
    return {
      open: shown.filter(isOpenForEntry),
      battles: all.filter((m) => m.mode === 'trend_battle'),
      rest: shown.filter((m) => !isOpenForEntry(m)),
    }
  }, [state, filter])

  return (
    <>
      <header className="page-head">
        <div>
          <h1>{battlesOnly ? 'Trend Battles' : 'Markets'}</h1>
          <p>{battlesOnly ? 'Two topics. One attention metric. Settled from public evidence.' : 'Onchain attention markets on NEAR Testnet. Test assets have no value.'}</p>
        </div>
      </header>

      {!battlesOnly && (
        <div className="seg" role="tablist" aria-label="Filter markets">
          {FILTERS.map((f) => (
            <button key={f.id} role="tab" aria-selected={filter === f.id} className="seg-btn"
              onClick={() => setParams(f.id === 'all' ? {} : { f: f.id }, { replace: true })}>{f.label}</button>
          ))}
        </div>
      )}

      {state.status === 'loading' && <SkeletonList />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (
        <>
          {open.length > 0 && (
            <section className="msec" aria-labelledby="sec-open">
              <h2 id="sec-open" className="msec-h">Open predictions</h2>
              <div className="mgrid">{open.map((m) => <MarketRow key={m.market_id} m={m} />)}</div>
            </section>
          )}

          {filter === 'all' && battles.length > 0 && (
            <section className="msec" aria-labelledby="sec-battles">
              <h2 id="sec-battles" className="msec-h">Trend Battles</h2>
              <div className="mgrid">{battles.map((m) => <MarketRow key={m.market_id} m={m} />)}</div>
            </section>
          )}

          {(() => {
            const list = filter === 'all' ? rest.filter((m) => m.mode !== 'trend_battle') : rest
            if (!list.length) return null
            return (
              <section className="msec" aria-labelledby="sec-rest">
                <h2 id="sec-rest" className="msec-h">{filter === 'all' ? 'Resolved demonstrations & closed' : 'Markets'}</h2>
                <div className="mgrid">{list.map((m) => <MarketRow key={m.market_id} m={m} />)}</div>
              </section>
            )
          })()}

          {open.length === 0 && rest.length === 0 && (
            <div className="state">
              <h2>No markets match</h2>
              <p>{filter === 'open' ? 'No future-outcome market is open for entries right now.' : 'There are no onchain markets in this view.'}</p>
            </div>
          )}
        </>
      )}
    </>
  )
}
