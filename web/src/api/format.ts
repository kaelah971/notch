// Base-unit formatting with BigInt only. Never floats for settlement amounts.

/** Truncates (never rounds up) to maxFraction digits. */
export function formatUnits(raw: string, decimals: number, maxFraction = 2): string {
  const neg = raw.startsWith('-')
  const v = BigInt(neg ? raw.slice(1) : raw)
  const base = 10n ** BigInt(decimals)
  const whole = (v / base).toLocaleString('en-US')
  const frac = (v % base).toString().padStart(decimals, '0').slice(0, maxFraction).replace(/0+$/, '')
  return `${neg ? '-' : ''}${whole}${frac ? '.' + frac : ''}`
}

/** Parse a user-entered decimal string into base units. Returns null when invalid. */
export function parseUnits(input: string, decimals: number): string | null {
  const s = input.trim()
  if (!/^\d+(\.\d+)?$/.test(s)) return null
  const [w, f = ''] = s.split('.')
  if (f.length > decimals) return null
  return (BigInt(w) * 10n ** BigInt(decimals) + BigInt(f.padEnd(decimals, '0') || '0')).toString()
}

export const sumUnits = (xs: string[]) => xs.reduce((a, b) => a + BigInt(b), 0n).toString()

/** Share of the pool in whole basis points (BigInt). Null when the pool is empty. This is pool composition, not odds. */
export function shareBps(part: string, total: string): number | null {
  const t = BigInt(total)
  if (t === 0n) return null
  return Number((BigInt(part) * 10000n) / t)
}

export function formatUtc(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short',
  })
}

export function relativeTo(iso: string, now = Date.now()): string {
  const ms = new Date(iso).getTime() - now
  const abs = Math.abs(ms)
  const units: [number, string][] = [[86400000, 'd'], [3600000, 'h'], [60000, 'm']]
  for (const [u, l] of units) if (abs >= u) { const n = Math.floor(abs / u); return ms > 0 ? `in ${n}${l}` : `${n}${l} ago` }
  return ms > 0 ? 'in <1m' : 'just now'
}

/** Strip the API's replay/forecast prefixes for display. Status is always shown separately via StatusBadge. */
export function cleanQuestion(q: string): string {
  return q.replace(/^(HISTORICAL REPLAY \(not a forecast\)|FORECAST \(not a replay\)):\s*/i, '')
}

export const USDC_DECIMALS = 6
