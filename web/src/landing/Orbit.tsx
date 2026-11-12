import { useEffect, useRef } from 'react'
import type { Collectible } from './collectibles'

/**
 * Ref 02: illustrated tiles on a tilted elliptical orbit around the headline.
 * Objects stay upright; depth (sin of angle) drives scale, blur, opacity and z-order.
 * Transforms/filters only — no layout work per frame. Reduced motion: static placement.
 */
export function Orbit({ items }: { items: Collectible[] }) {
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = root.current
    if (!el || !items.length) return
    const nodes = Array.from(el.querySelectorAll<HTMLElement>('.orb'))
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)')
    const PERIOD = 64_000 // ms per revolution — slow and calm
    let raf = 0
    let w = el.clientWidth, h = el.clientHeight
    const ro = new ResizeObserver(() => { w = el.clientWidth; h = el.clientHeight; if (reduce.matches) place(0) })
    ro.observe(el)

    function place(t: number) {
      const rx = Math.min(w * 0.42, 620)
      const ry = Math.min(h * 0.40, 330)
      const base = (t / PERIOD) * Math.PI * 2
      nodes.forEach((n, i) => {
        const a = base + (i / nodes.length) * Math.PI * 2
        const x = Math.cos(a) * rx
        const y = Math.sin(a) * ry * 0.92 + Math.cos(a) * ry * 0.18 // slight tilt
        const depth = (Math.sin(a) + 1) / 2 // 0 = far (top), 1 = near (bottom)
        const s = 0.62 + depth * 0.5
        const blur = (1 - depth) * 5 + (depth > 0.85 ? (depth - 0.85) * 18 : 0) // far & very-near are soft: depth of field
        n.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%) scale(${s})`
        // Quantise blur to 0.5px steps: fewer filter re-rasterisations on low-end GPUs.
        const qb = Math.round(blur * 2) / 2
        if (n.dataset.b !== String(qb)) { n.dataset.b = String(qb); n.style.filter = qb ? `blur(${qb}px)` : 'none' }
        n.style.opacity = (0.35 + depth * 0.65).toFixed(3)
        n.style.zIndex = String(Math.round(depth * 100))
        // Trail points opposite to motion (tangent of the ellipse).
        const tx = -Math.sin(a) * rx, ty = Math.cos(a) * ry
        const trail = n.querySelector<HTMLElement>('.orb-trail')
        if (trail) trail.style.transform = `rotate(${Math.atan2(-ty, -tx)}rad)`
      })
    }

    const loop = (now: number) => { place(now); raf = requestAnimationFrame(loop) }
    const start = () => { cancelAnimationFrame(raf); if (reduce.matches) place(0); else raf = requestAnimationFrame(loop) }
    start()
    reduce.addEventListener('change', start)
    const vis = () => { if (document.hidden) cancelAnimationFrame(raf); else start() }
    document.addEventListener('visibilitychange', vis)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); reduce.removeEventListener('change', start); document.removeEventListener('visibilitychange', vis) }
  }, [items])

  if (!items.length) return null
  return (
    <div className="orbit" ref={root} aria-hidden>
      {items.map((c) => (
        <div key={c.id} className="orb" style={{ ['--glow' as string]: c.glow }}>
          <span className="orb-trail" />
          <img src={c.src} alt="" draggable={false} />
        </div>
      ))}
    </div>
  )
}
