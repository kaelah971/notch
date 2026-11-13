import { useEffect, useMemo, useRef, useState } from 'react'
import './AttentionChart.css'

/**
 * Interactive attention chart (design ref 05). Data: real daily Wikipedia pageviews from the
 * Wikimedia Analytics API — the source, project, access and agent the market rule settles on.
 *
 * Presentation: a smooth monotone curve through the real daily observations. The selection
 * always snaps to an actual observation; the readout, dot and timestamp never show an
 * interpolated value. Daily granularity only — no intraday points are invented.
 */
interface Pt { t: number; v: number }
interface Series { article: string; label: string; points: Pt[] }
type Range = 7 | 30 | 90 | 365 | 0
const RANGES: { d: Range; label: string }[] = [
  { d: 7, label: '7D' }, { d: 30, label: '30D' }, { d: 90, label: '90D' }, { d: 365, label: '1Y' }, { d: 0, label: 'All' },
]
const DAY = 86_400_000
const WIKIMEDIA_START = Date.UTC(2015, 6, 1) // per-article daily pageviews begin July 2015
const LINE = ['var(--chart-a)', 'var(--chart-b)']

const ymd = (t: number) => new Date(t).toISOString().slice(0, 10)
const stamp = (t: number) => ymd(t).replace(/-/g, '') + '00'
const fmtDay = (t: number, long: boolean) => new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', ...(long ? { year: 'numeric' } : {}), timeZone: 'UTC' })
const nf = (v: number, d = 0) => v.toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d })

async function fetchViews(project: string, article: string, start: number, end: number, signal: AbortSignal): Promise<Pt[]> {
  const url = `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/${project}/all-access/user/${encodeURIComponent(article)}/daily/${stamp(start)}/${stamp(end)}`
  const r = await fetch(url, { signal })
  if (r.status === 404) return []
  if (!r.ok) throw new Error(`Wikimedia ${r.status}`)
  const j = (await r.json()) as { items: { timestamp: string; views: number }[] }
  return j.items.map((i) => ({ t: Date.UTC(+i.timestamp.slice(0, 4), +i.timestamp.slice(4, 6) - 1, +i.timestamp.slice(6, 8)), v: i.views }))
}

/** Fritsch–Carlson monotone cubic: smooth, never overshoots between real observations. */
function smoothPath(xy: [number, number][]): string {
  const n = xy.length
  if (n === 0) return ''
  if (n === 1) return `M${xy[0][0]},${xy[0][1]}`
  const dx: number[] = [], m: number[] = []
  for (let i = 0; i < n - 1; i++) { dx[i] = xy[i + 1][0] - xy[i][0]; m[i] = (xy[i + 1][1] - xy[i][1]) / (dx[i] || 1) }
  const tg = [m[0]]
  for (let i = 1; i < n - 1; i++) tg[i] = m[i - 1] * m[i] <= 0 ? 0 : (3 * (dx[i - 1] + dx[i])) / ((2 * dx[i] + dx[i - 1]) / m[i - 1] + (dx[i] + 2 * dx[i - 1]) / m[i])
  tg[n - 1] = m[n - 2]
  let d = `M${xy[0][0].toFixed(1)},${xy[0][1].toFixed(1)}`
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3
    d += `C${(xy[i][0] + h).toFixed(1)},${(xy[i][1] + h * tg[i]).toFixed(1)} ${(xy[i + 1][0] - h).toFixed(1)},${(xy[i + 1][1] - h * tg[i + 1]).toFixed(1)} ${xy[i + 1][0].toFixed(1)},${xy[i + 1][1].toFixed(1)}`
  }
  return d
}

const niceTicks = (lo: number, hi: number, n = 4) => {
  const span = hi - lo || 1
  const step0 = span / n
  const mag = 10 ** Math.floor(Math.log10(step0))
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= step0) ?? step0
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v)
  return out
}

export interface ChartMarker { date: string; label: string }

export function AttentionChart({ project = 'en.wikipedia.org', articles, markers = [], thresholdPct, baselineDate, defaultRange = 30 }: {
  project?: string
  articles: { article: string; label: string }[]
  markers?: ChartMarker[]
  /** Trend Trading: target level = baseline-day views × (1 + threshold), drawn once the baseline day exists. */
  thresholdPct?: string
  /** Rule baseline day (YYYY-MM-DD). Used for "change vs baseline" and for battle normalisation. */
  baselineDate?: string
  defaultRange?: Range
}) {
  const [range, setRange] = useState<Range>(defaultRange)
  const [raw, setRaw] = useState<Series[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sel, setSel] = useState<number | null>(null) // index into the shared timeline; null = latest
  const plot = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const key = articles.map((a) => a.article).join('|')
  const battle = articles.length > 1

  useEffect(() => {
    const ac = new AbortController()
    const end = Date.now() - DAY // Wikimedia publishes the previous full UTC day
    const start = range === 0 ? WIKIMEDIA_START : end - range * DAY
    setErr(null); setSel(null)
    Promise.all(articles.map(async (a) => ({ ...a, points: await fetchViews(project, a.article, start, end, ac.signal) })))
      .then(setRaw, (e) => { if (!ac.signal.aborted) setErr(String(e.message ?? e)) })
    // Refresh when a new daily observation is likely published (hourly check, tab visible only).
    const h = window.setInterval(() => {
      if (document.hidden) return
      Promise.all(articles.map(async (a) => ({ ...a, points: await fetchViews(project, a.article, start, Date.now() - DAY, ac.signal) })))
        .then((next) => setRaw((cur) => (cur && next[0]?.points.length !== cur[0]?.points.length ? next : cur)), () => {})
    }, 3_600_000)
    return () => { ac.abort(); clearInterval(h) }
  }, [key, range, project]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Shared daily timeline. Battles are normalised to an index (reference day = 100), matching the rule's growth comparison. */
  const model = useMemo(() => {
    if (!raw || !raw.some((s) => s.points.length)) return null
    const times = [...new Set(raw.flatMap((s) => s.points.map((p) => p.t)))].sort((a, b) => a - b)
    const refT = baselineDate && times.includes(Date.parse(baselineDate)) ? Date.parse(baselineDate) : times[0]
    const series = raw.map((s) => {
      const byT = new Map(s.points.map((p) => [p.t, p.v]))
      const ref = byT.get(refT)
      const vals = times.map((t) => {
        const v = byT.get(t)
        if (v == null) return null
        return battle ? (ref ? (v / ref) * 100 : null) : v
      })
      return { ...s, vals, ref }
    })
    const all = series.flatMap((s) => s.vals.filter((v): v is number => v != null))
    const base = !battle ? series[0].ref : undefined
    const level = !battle && base != null && thresholdPct && baselineDate && refT === Date.parse(baselineDate) ? base * (1 + Number(thresholdPct) / 100) : null
    let lo = Math.min(...all, level ?? Infinity), hi = Math.max(...all, level ?? -Infinity)
    const pad = (hi - lo) * 0.12 || hi * 0.1 || 1
    lo = Math.max(0, lo - pad); hi = hi + pad
    return { times, series, refT, level, lo, hi, ticks: niceTicks(lo, hi) }
  }, [raw, battle, baselineDate, thresholdPct])

  const W = 1000, H = 300
  const x = (i: number) => model ? (model.times.length < 2 ? W / 2 : (i / (model.times.length - 1)) * W) : 0
  const y = (v: number) => model ? H - ((v - model.lo) / (model.hi - model.lo)) * H : 0
  const last = model ? model.times.length - 1 : 0
  const idx = sel ?? last
  const inspecting = sel != null && sel !== last

  function pick(clientX: number) {
    if (!plot.current || !model) return
    const r = plot.current.getBoundingClientRect()
    const f = Math.min(1, Math.max(0, (clientX - r.left) / r.width))
    setSel(Math.round(f * last)) // snap to a real daily observation
  }
  const onDown = (e: React.PointerEvent) => { dragging.current = true; plot.current?.setPointerCapture(e.pointerId); pick(e.clientX) }
  const onMove = (e: React.PointerEvent) => { if (e.pointerType === 'mouse' || dragging.current) pick(e.clientX) }
  const onUp = (e: React.PointerEvent) => { dragging.current = false; plot.current?.releasePointerCapture?.(e.pointerId); if (e.pointerType !== 'mouse') setSel(null) }
  const onKey = (e: React.KeyboardEvent) => {
    if (!model) return
    if (e.key === 'ArrowLeft') { e.preventDefault(); setSel(Math.max(0, idx - 1)) }
    else if (e.key === 'ArrowRight') { e.preventDefault(); const n = Math.min(last, idx + 1); setSel(n === last ? null : n) }
    else if (e.key === 'Home') { e.preventDefault(); setSel(0) }
    else if (e.key === 'End' || e.key === 'Escape') { e.preventDefault(); setSel(null) }
  }

  // Headline: latest observation and change vs the rule baseline (or range start).
  const head = model?.series.map((s) => {
    const latestI = s.vals.reduce<number>((acc, v, i) => (v != null ? i : acc), -1)
    const latest = latestI >= 0 ? s.vals[latestI]! : null
    const ref = battle ? 100 : s.ref ?? null
    const chg = latest != null && ref ? ((latest - ref) / ref) * 100 : null
    return { label: s.label, latest, chg }
  })
  const refLabel = model ? (baselineDate && model.refT === Date.parse(baselineDate) ? `vs baseline ${fmtDay(model.refT, false)}` : `vs ${fmtDay(model.refT, false)}`) : ''
  const unit = battle ? 'Attention index' : 'Daily views'
  const fmtV = (v: number) => (battle ? nf(v, 1) : nf(v))

  // X labels: sparse when idle (start · now), denser while inspecting (ref behaviour).
  const xTicks = model ? (inspecting ? [0, 0.25, 0.5, 0.75].map((f) => Math.round(f * last)) : [0]) : []

  return (
    <div className="achart">
      <div className="achart-head">
        <div className="achart-big">
          {head?.map((h, i) => (
            <div key={h.label} className="achart-bigrow">
              {battle && <span className="achart-swatch" style={{ background: LINE[i] }} aria-hidden />}
              <span className="achart-bignum num">{h.latest != null ? fmtV(h.latest) : '—'}</span>
              {h.chg != null && <span className={`achart-chg ${h.chg >= 0 ? 'up' : 'down'}`}>{h.chg >= 0 ? '+' : ''}{nf(h.chg, 1)}%</span>}
              {battle && <span className="achart-bigl">{h.label}</span>}
            </div>
          ))}
          {model && (
            <p className="achart-sub">
              <span className="achart-freshness" aria-label={`Latest observation: ${fmtDay(model.times[last], true)} UTC`}>
                <span className="achart-freshness-label">Latest observation</span>
                <time dateTime={ymd(model.times[last])}>{fmtDay(model.times[last], true)} UTC</time>
              </span>
              <span className="achart-freshness-note">Daily data · not a live price feed</span>
              <span> · {battle ? 'Index, reference day = 100' : `${articles[0].label} · daily views`} · change {refLabel}</span>
            </p>
          )}
        </div>
        <div className="seg seg-sm" role="group" aria-label="Time range">
          {RANGES.map((r) => <button key={r.d} aria-pressed={range === r.d} className="seg-btn" onClick={() => setRange(r.d)}>{r.label}</button>)}
        </div>
      </div>

      {err && <p className="dim achart-msg" role="alert">Pageview data is unavailable right now ({err}).</p>}
      {!err && !raw && <div className="skeleton" style={{ height: 260 }} aria-busy="true" />}
      {!err && raw && !model && <p className="dim achart-msg">No published pageview data in this range yet.</p>}

      {model && (
        <>
          <div className="achart-readout" aria-live="polite">
            <span className="achart-rbar" aria-hidden />
            <div>
              <span className="achart-rl">{unit}{inspecting ? ` · ${fmtDay(model.times[idx], true)}` : ' · latest'}</span>
              <span className="achart-rv num">
                {model.series.map((s, i) => (
                  <span key={s.label}>{battle && <i style={{ background: LINE[i] }} />}{s.vals[idx] != null ? fmtV(s.vals[idx]!) : 'no data'}</span>
                ))}
              </span>
            </div>
          </div>

          <div className="achart-frame">
            <div className="achart-y" aria-hidden>
              {model.ticks.map((tv) => <span key={tv} style={{ top: `${(y(tv) / H) * 100}%` }}>{tv >= 10000 ? `${nf(tv / 1000)}k` : nf(tv)}</span>)}
            </div>
            <div className="achart-plot" ref={plot} tabIndex={0} role="slider"
              aria-label={`${unit} over time. Use arrow keys to inspect days.`}
              aria-valuemin={0} aria-valuemax={last} aria-valuenow={idx}
              aria-valuetext={`${fmtDay(model.times[idx], true)}: ${model.series.map((s) => `${s.label} ${s.vals[idx] != null ? fmtV(s.vals[idx]!) : 'no data'}`).join(', ')}`}
              onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
              onPointerLeave={(e) => { if (e.pointerType === 'mouse') setSel(null) }} onKeyDown={onKey}>
              <div className="achart-stamp" style={{ left: `${(x(idx) / W) * 100}%` }}>{inspecting ? fmtDay(model.times[idx], false) : 'Latest'}</div>
              <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
                <defs>
                  <clipPath id={`clip-${key.replace(/\W/g, '')}`}><rect x={0} y={-10} width={x(idx)} height={H + 20} /></clipPath>
                </defs>
                {model.ticks.map((tv) => <line key={tv} x1={0} x2={W} y1={y(tv)} y2={y(tv)} className="achart-grid" />)}
                {markers.map((mk) => {
                  const i = model.times.indexOf(Date.parse(mk.date))
                  return i < 0 ? null : <line key={mk.label} x1={x(i)} x2={x(i)} y1={0} y2={H} className="achart-marker" />
                })}
                {model.level != null && <line x1={0} x2={W} y1={y(model.level)} y2={y(model.level)} className="achart-level" />}
                {model.series.map((s, si) => {
                  const pts = s.vals.map((v, i) => (v == null ? null : [x(i), y(v)] as [number, number])).filter((p): p is [number, number] => !!p)
                  const d = smoothPath(pts)
                  return (
                    <g key={s.label}>
                      <path d={d} className="achart-line is-dim" />
                      <path d={d} className="achart-line" style={{ stroke: LINE[si] }} clipPath={`url(#clip-${key.replace(/\W/g, '')})`} />
                    </g>
                  )
                })}
                <line x1={x(idx)} x2={x(idx)} y1={0} y2={H} className="achart-cursor" />
              </svg>
              {model.series.map((s, si) => s.vals[idx] != null && (
                <span key={s.label} className="achart-dot" style={{ left: `${(x(idx) / W) * 100}%`, top: `${(y(s.vals[idx]!) / H) * 100}%`, background: LINE[si] }} aria-hidden />
              ))}
            </div>
          </div>
          <div className="achart-x" aria-hidden>
            {xTicks.map((i) => <span key={i} style={{ left: `${(x(i) / W) * 100}%` }}>{fmtDay(model.times[i], range === 0 || range === 365)}</span>)}
            {!inspecting && <span className="achart-x-mid">Date (UTC)</span>}
            <span className="achart-x-end">Now</span>
          </div>
        </>
      )}

      <p className="fine">
        Real daily observations from Wikimedia Pageviews · {project} · all-access · user — the source the rule settles on. The curve is smoothed for display; inspected values are actual daily counts.
        {markers.length > 0 && <> Dashed lines: {markers.map((mk) => `${mk.label} ${mk.date}`).join(', ')}.</>}
        {model?.level != null && <> Yellow line: views needed on the target day ({nf(Math.ceil(model.level))}).</>}
        {' '}Attention data — not a price or probability.
      </p>
    </div>
  )
}
