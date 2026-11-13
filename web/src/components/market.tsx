import { Link } from 'react-router-dom'
import type { Market } from '../api/types'
import { cleanQuestion, formatUnits, formatUtc, relativeTo, shareBps, sumUnits, USDC_DECIMALS } from '../api/format'
import { ShareMarketButton } from '../share/ShareButtons'
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

export interface ParsedRule {
  topic: string
  /** Growth threshold in percent (trend_trading only). */
  thresholdPct?: string
  baseline: string
  target: string
  days: number
}

/**
 * Parse the canonical onchain question (S3B oracle template). Titles are derived from these
 * exact fields so copy can never change a market's meaning. Returns null for unknown templates.
 */
export function parseRule(m: Market): ParsedRule | null {
  const q = cleanQuestion(m.question)
  const t = q.match(/pageviews for (.+?) grow by at least ([\d.]+)% on the full UTC day (\d{4}-\d{2}-\d{2}) versus the full UTC day (\d{4}-\d{2}-\d{2})/i)
  if (t) return { topic: t[1], thresholdPct: String(Number(t[2])), target: t[3], baseline: t[4], days: dayDiff(t[4], t[3]) }
  const b = q.match(/growth from the full UTC day (\d{4}-\d{2}-\d{2}) to the full UTC day (\d{4}-\d{2}-\d{2})/i)
  if (b && m.battle) return { topic: `${m.battle.topic_a.article_title} vs ${m.battle.topic_b.article_title}`, baseline: b[1], target: b[2], days: dayDiff(b[1], b[2]) }
  return null
}
const dayDiff = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000)
const span = (d: number) => (d === 7 ? 'in one week' : `in ${d} days`)

/** Readable headline derived from the locked rule. Replays are phrased in the past tense. */
export function marketTitle(m: Market): string {
  const r = parseRule(m)
  const past = m.is_historical_replay
  if (m.battle) {
    const a = m.battle.topic_a.article_title, b = m.battle.topic_b.article_title
    return past ? `${a} vs ${b}: whose attention grew faster?` : `${a} vs ${b}: whose attention will grow faster?`
  }
  if (r?.thresholdPct) {
    return past ? `Did ${r.topic}’s attention jump ${r.thresholdPct}% ${span(r.days)}?` : `Will ${r.topic}’s attention jump ${r.thresholdPct}% ${span(r.days)}?`
  }
  return r?.topic ?? m.market_id
}

/** Category shown on cards: what is measured, from the rule source. */
export const marketCategory = (m: Market) => (m.source_id.startsWith('wikimedia') ? 'Wikipedia attention' : m.source_id)

export const totalPool = (m: Market) => m.totals.reduce((a, b) => a + BigInt(b), 0n)

/** Pool composition per choice from onchain totals. This is stake distribution, not odds. */
export function PoolBars({ m }: { m: Market }) {
  const total = sumUnits(m.totals)
  return (
    <div className="pool">
      <div className="pool-head">
        <span>Total staked</span>
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
  return <div className="mrow-wrap"><MarketRowLink m={m} /><ShareMarketButton m={m} compact /></div>
}

function MarketRowLink({ m }: { m: Market }) {
  const total = sumUnits(m.totals)
  return (
    <Link to={`/app/markets/${encodeURIComponent(m.market_id)}`} className={`mrow${m.is_historical_replay ? ' is-replay' : isOpenForEntry(m) ? ' is-open' : ''}`}>
      <div className="mrow-top">
        <span className="mrow-mode">{modeLabel(m)} · {marketCategory(m)}</span>
        <StatusBadge m={m} />
      </div>
      <h3 className="mrow-title">{marketTitle(m)}</h3>
      <p className="mrow-q">{cleanQuestion(m.question)}</p>
      {total !== '0' && (
        <div className="mrow-split" aria-label="Stake distribution">
          {m.choices.map((c, i) => {
            const bps = shareBps(m.totals[i] ?? '0', total) ?? 0
            return <span key={c} style={{ flexGrow: bps || 1 }} className={m.winning_outcome === i ? 'is-won' : ''} title={`${c}: ${formatUnits(m.totals[i] ?? '0', USDC_DECIMALS)} USDC staked`}>{c}</span>
          })}
        </div>
      )}
      <div className="mrow-foot">
        {isOpenForEntry(m)
          ? <span>Entries close <time dateTime={m.close_at_utc}>{relativeTo(m.close_at_utc)}</time></span>
          : m.winning_choice
            ? <span>Outcome: <strong>{m.winning_choice}</strong></span>
            : <span>Closed {formatUtc(m.close_at_utc)}</span>}
        <span className="mono">{formatUnits(sumUnits(m.totals), USDC_DECIMALS)} test-USDC staked</span>
      </div>
    </Link>
  )
}
