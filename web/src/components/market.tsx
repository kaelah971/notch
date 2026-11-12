import { Link } from 'react-router-dom'
import type { Market } from '../api/types'
import { cleanQuestion, formatUnits, formatUtc, relativeTo, shareBps, sumUnits, USDC_DECIMALS } from '../api/format'
import './market.css'

export const isOpenForEntry = (m: Market) => m.display_status === 'open_future' && m.entries_open && !m.entries_paused

export function StatusBadge({ m }: { m: Market }) {
  switch (m.display_status) {
    case 'open_future':
      return m.entries_paused ? <span className="badge">Entries paused</span> : <span className="badge badge-live">Open prediction</span>
    case 'closed': return <span className="badge">Closed · awaiting resolution</span>
    case 'resolved': return <span className="badge">Resolved</span>
    case 'voided': return <span className="badge">Voided</span>
    default: return <span className="badge badge-replay">Resolved demonstration</span>
  }
}

export const modeLabel = (m: Market) => (m.mode === 'trend_battle' ? 'Trend Battle' : 'Trend Trading')

/** Short display title derived from real market fields — never invented. */
export function marketTitle(m: Market): string {
  if (m.battle) return `${m.battle.topic_a.article_title} vs ${m.battle.topic_b.article_title}`
  const match = cleanQuestion(m.question).match(/pageviews for (.+?) (grow|fall|drop)/i)
  return match ? match[1] : m.market_id
}

/** Pool composition per choice from onchain totals. This is stake distribution, not odds. */
export function PoolBars({ m }: { m: Market }) {
  const total = sumUnits(m.totals)
  return (
    <div className="pool">
      <div className="pool-head">
        <span>Pool</span>
        <span className="mono">{formatUnits(total, USDC_DECIMALS)} test-USDC</span>
      </div>
      {m.choices.map((c, i) => {
        const bps = shareBps(m.totals[i] ?? '0', total)
        const won = m.winning_outcome === i
        return (
          <div key={c} className={`pool-row${won ? ' is-won' : ''}`}>
            <span className="pool-choice">{c}{won && <span className="pool-win">Winner</span>}</span>
            <span className="pool-bar" aria-hidden><span style={{ width: bps == null ? 0 : `${bps / 100}%` }} /></span>
            <span className="mono pool-amt">{formatUnits(m.totals[i] ?? '0', USDC_DECIMALS)}</span>
          </div>
        )
      })}
      {total === '0' && <p className="pool-empty">No stakes yet.</p>}
    </div>
  )
}

export function MarketRow({ m }: { m: Market }) {
  return (
    <Link to={`/app/markets/${encodeURIComponent(m.market_id)}`} className="mrow">
      <div className="mrow-top">
        <span className="mrow-mode">{modeLabel(m)}</span>
        <StatusBadge m={m} />
      </div>
      <h3 className="mrow-title">{marketTitle(m)}</h3>
      <p className="mrow-q">{cleanQuestion(m.question)}</p>
      <div className="mrow-foot">
        {isOpenForEntry(m)
          ? <span>Entries close <time dateTime={m.close_at_utc}>{relativeTo(m.close_at_utc)}</time></span>
          : m.winning_choice
            ? <span>Outcome: <strong>{m.winning_choice}</strong></span>
            : <span>Closed {formatUtc(m.close_at_utc)}</span>}
        <span className="mono">{formatUnits(sumUnits(m.totals), USDC_DECIMALS)} USDC pooled</span>
      </div>
    </Link>
  )
}
