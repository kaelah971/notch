// Follows are stored on this device only (no social backend exists yet). Nothing is published.
const KEY = 'notch.signals.following'
export const FOLLOWING_CHANGED = 'notch-following-changed'

export function getFollowing(): string[] {
  try { const v = JSON.parse(localStorage.getItem(KEY) ?? '[]'); return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [] } catch { return [] }
}
export function setFollowing(ids: string[]) {
  const next = [...new Set(ids)].slice(0, 100)
  try { localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* storage unavailable */ }
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(FOLLOWING_CHANGED))
}
export function toggleFollow(id: string): boolean {
  const cur = getFollowing()
  const on = !cur.includes(id)
  setFollowing(on ? [...cur, id] : cur.filter((x) => x !== id))
  return on
}

export const isNearAccount = (s: string) =>
  /^(([a-z\d]+[-_])*[a-z\d]+\.)*([a-z\d]+[-_])*[a-z\d]+$/.test(s) && s.length >= 2 && s.length <= 64
