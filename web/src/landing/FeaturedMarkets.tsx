import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market } from '../api/types'
import { formatUnits, relativeTo, sumUnits, USDC_DECIMALS } from '../api/format'
import { isOpenForEntry, marketTitle, modeLabel } from '../components/market'
import { collectibles } from './collectibles'

// Ref 03 card palettes, warmed toward the Sunburst family.
const PALETTES = [
  'linear-gradient(160deg, #8fd8ff 0%, #5aa0ff 55%, #b98cff 100%)',
  'linear-gradient(170deg, #fff6c2 0%, #fceb53 40%, #f49f04 100%)',
  'linear-gradient(160deg, #7fb2ff 0%, #ff9a8b 70%, #ffc06b 100%)',
]

function pick(markets: Market[]): Market[] {
  const open = markets.filter(isOpenForEntry)
  const battle = markets.filter((m) => m.mode === 'trend_battle' && !open.includes(m))
  const rest = markets.filter((m) => !open.includes(m) && !battle.includes(m))
  return [...battle, ...open, ...rest].slice(0, 3) // open (if any) lands in the centre
}

function Card({ m, i }: { m: Market; i: number }) {
  const open = isOpenForEntry(m)
  const art = collectibles[i % Math.max(collectibles.length, 1)]
  return (
    <Link to={`/app/markets/${encodeURIComponent(m.market_id)}`} className={`fcard fcard-${i}`} style={{ background: PALETTES[i % 3] }}>
      <div className="fcard-top">
        <div>
          <p className="fcard-title">{marketTitle(m)}</p>
          <p className="fcard-sub">{modeLabel(m)}</p>
        </div>
        <span className={`fcard-status${open ? ' is-open' : ''}`}>{open ? 'Open prediction' : 'Resolved demo'}</span>
      </div>
      <div className="fcard-row">
        <span>{open ? `Closes ${relativeTo(m.close_at_utc)}` : m.winning_choice ? `Outcome` : 'Closed'}</span>
        <strong>{open ? m.choices.join(' / ') : m.winning_choice ?? '—'}</strong>
      </div>
      <div className="fcard-row fcard-pool">
        <span>Pooled</span><strong className="mono">{formatUnits(sumUnits(m.totals), USDC_DECIMALS)} USDC</strong>
      </div>
      {art && <img className="fcard-art" src={art.src} alt="" aria-hidden />}
    </Link>
  )
}

export function FeaturedMarkets() {
  const [state] = useApi(() => api.markets(), [])
  return (
    <section className="featured" aria-labelledby="featured-h">
      <div className="featured-intro">
        <h2 id="featured-h">Real markets.<br />Real evidence.</h2>
        <p>Every market reads from the NEAR Testnet contract and settles against a frozen public data rule. Resolved demonstrations are labelled as history, never as predictions.</p>
        <Link to="/app/markets" className="btn btn-primary">Explore Markets</Link>
      </div>
      <div className="fstack">
        {state.status === 'loading' && <div className="skeleton" style={{ height: 420, width: 320, borderRadius: 36 }} />}
        {state.status === 'error' && <p className="dim">Markets are unavailable right now.</p>}
        {state.status === 'ok' && (state.data.data.length
          ? pick(state.data.data).map((m, i) => <Card key={m.market_id} m={m} i={i} />)
          : <p className="dim">No onchain markets yet.</p>)}
      </div>
    </section>
  )
}
