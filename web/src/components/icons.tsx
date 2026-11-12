import type { SVGProps } from 'react'

/** Ref 04 "Markets" glyph: four outlined circles. Lucide has no exact match, so it's drawn at the same 1.5 stroke. */
export function MarketsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width={22} height={22} fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden {...props}>
      <circle cx="7.5" cy="7.5" r="3.5" /><circle cx="16.5" cy="7.5" r="3.5" />
      <circle cx="7.5" cy="16.5" r="3.5" /><circle cx="16.5" cy="16.5" r="3.5" />
    </svg>
  )
}

/** Notch mark: chart line in a rounded square (ref 04 logo tile). */
export function NotchMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width={22} height={22} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden {...props}>
      <rect x="3" y="3" width="18" height="18" rx="5" />
      <path d="M7 15l3.2-4 3 3L17 9" />
    </svg>
  )
}
