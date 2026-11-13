import { useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market } from '../api/types'
import { formatUnits, shareBps, USDC_DECIMALS } from '../api/format'
import './AttentionChart.css'

type Range = '24h' | '7d' | 'all'
const RANGES: { id: Range; label: string; ms: number }[] = [
  { id: '24h', label: '24H', ms: 86_400_000 }, { id: '7d', label: '7D', ms: 7 * 86_400_000 }, { id: 'all', label: 'All', ms: Infinity },
]

/**
 * Stake distribution over time, from pool totals the API actually observed onchain.
 * Drawn as a step line (a value holds until the next observation). No interpolation,
 * no points before recording began. This is participation, not a probability or price.
 */
export function ParticipationChart({ m }: { m: Market }) {
  const [hist] = useApi(() => api.marketHistory(m.market_id), [m.market_id, m.totals.join(',')])
  const [range, setRange] = useState<Range>('all')
  const [hover, setHover] = useState<number | null>(null)
  const box = useRef<HTMLDivElement>(null)

  const pts = useMemo(() => {
    if (hist.status !== 'ok') return []
    const cut = Date.now() - (RANGES.find((r) => r.id === range)?.ms ?? Infinity)
    return hist.data.data
      .map((p) => {
        const total = p.totals.reduce((a, b) => a + BigInt(b), 0n)
        return { t: Date.parse(p.observed_at_utc), total, first: BigInt(p.totals[0] ?? '0'), totals: p.totals }
      })
      .filter((p) => p.t >= cut)
  }, [hist, range])
  const staked = pts.filter((p) => p.total > 0n)
  const currentTotal = m.totals.reduce((a, b) => a + BigInt(b), 0n)
  const currentShares = currentTotal > 0n
    ? m.choices.map((choice, i) => ({ choice, bps: shareBps(m.totals[i] ?? '0', currentTotal.toString()) })).filter((x): x is { choice: string; bps: number } => x.bps != null && x.bps > 0)
    : []
  const formatPercent = (bps: number) => `${bps % 100 === 0 ? bps / 100 : (bps / 100).toFixed(2).replace(/0+$/, '').replace(/\.$/, '')}%`
  const currentSummary = currentShares.length === 1
    ? `${formatPercent(currentShares[0].bps)} of current stakes are on ${currentShares[0].choice}`
    : currentShares.map((x) => `${x.choice} ${formatPercent(x.bps)}`).join(' · ')
  const singleSnapshot = staked.length === 1

  const W = 800, H = 200
  const t0 = pts[0]?.t ?? 0, t1 = Math.max(Date.now(), pts.at(-1)?.t ?? 0)
  const x = (t: number) => ((t - t0) / Math.max(t1 - t0, 1)) * W
  const y = (bps: number) => H - (bps / 10000) * H
  const share = (p: { first: bigint; total: bigint }) => (p.total === 0n ? null : Number((p.first * 10000n) / p.total))

  // Step path over observations with stake; gaps where the pool was empty.
  let d = ''
  pts.forEach((p, i) => {
    const s = share(p)
    if (s == null) return
    const next = pts[i + 1]?.t ?? t1
    d += `${d && share(pts[i - 1] ?? { first: 0n, total: 0n }) != null ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(s).toFixed(1)}H${x(next).toFixed(1)}`
  })

  function onMove(e: React.PointerEvent) {
    if (!box.current || !pts.length) return
    const r = box.current.getBoundingClientRect()
    const t = t0 + ((e.clientX - r.left) / r.width) * (t1 - t0)
    let idx = 0
    for (let i = 0; i < pts.length; i++) if (pts[i].t <= t) idx = i
    setHover(idx)
  }
  const hp = hover != null ? pts[hover] : null

  return (
    <div className="achart">
      <div className="achart-head">
        <div className="achart-legend"><span><i style={{ background: '#fceb53' }} />{m.choices[0]} share of total staked</span></div>
        <div className="seg seg-sm" role="group" aria-label="Time range">
          {RANGES.map((r) => <button key={r.id} aria-pressed={range === r.id} className="seg-btn" onClick={() => setRange(r.id)}>{r.label}</button>)}
        </div>
      </div>
      {hist.status === 'ok' && currentTotal > 0n && (
        <div className="participation-current" role="status">
          <strong>{currentSummary}</strong>
          <span>{singleSnapshot ? 'Participation history is still being collected; this is the current onchain snapshot.' : 'Current distribution from the market contract.'}</span>
        </div>
      )}
      {hist.status === 'loading' && <div className="skeleton" style={{ height: 160 }} />}
      {hist.status === 'error' && <p className="dim achart-msg">{hist.error.code === 'HTTP_404' || hist.error.status === 404 ? 'Participation history isn’t available from this API version yet.' : `Participation history is unavailable (${hist.error.message}).`}</p>}
      {hist.status === 'ok' && staked.length === 0 && (
        <p className="dim achart-msg">No stake observed {range === 'all' ? 'yet' : 'in this range'}. The line starts when the first position is recorded{pts.length ? ` — ${pts.length} observation${pts.length > 1 ? 's' : ''} of an empty pool so far` : ''}.</p>
      )}
      {hist.status === 'ok' && staked.length > 0 && (
        <div className="achart-plot is-simple" ref={box} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${m.choices[0]} share of stake over time`}>
            <line x1={0} x2={W} y1={H / 2} y2={H / 2} className="achart-grid" />
            {!singleSnapshot && <path d={d} fill="none" stroke="#fceb53" strokeWidth={2} vectorEffect="non-scaling-stroke" />}
            {pts.map((p, i) => share(p) != null && <circle key={i} cx={x(p.t)} cy={y(share(p)!)} r={3} fill="#fceb53" vectorEffect="non-scaling-stroke" />)}
            {hp && <line x1={x(hp.t)} x2={x(hp.t)} y1={0} y2={H} className="achart-cursor" />}
          </svg>
          {hp && (
            <div className="achart-tip" style={{ left: `${Math.min(92, Math.max(8, (x(hp.t) / W) * 100)).toFixed(1)}%` }}>
              <strong>{new Date(hp.t).toISOString().replace('T', ' ').slice(0, 16)} UTC</strong>
              {m.choices.map((c, i) => <span key={c}>{c}: {formatUnits(hp.totals[i] ?? '0', USDC_DECIMALS)} USDC</span>)}
            </div>
          )}
          <div className="achart-axis"><span>{new Date(t0).toISOString().slice(0, 10)}</span><span>50%</span><span>now</span></div>
        </div>
      )}
      <p className="fine">Recorded by the Notch API each time it reads this market’s pools from the contract (only when totals change, or hourly). History starts when recording began and isn’t backfilled. This shows how stake is split — not a probability or price.</p>
    </div>
  )
}
