import { api } from '../api/client'

const PENDING_KEY = 'notch.pendingEntry'
export interface PendingEntry { marketId: string; accountId: string; before: string; choice: string; stake: string; at: number }

export function savePending(p: PendingEntry) { try { sessionStorage.setItem(PENDING_KEY, JSON.stringify(p)) } catch { /* noop */ } }
export function loadPending(marketId: string): PendingEntry | null {
  try {
    const p = JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? 'null') as PendingEntry | null
    return p && p.marketId === marketId && Date.now() - p.at < 30 * 60_000 ? p : null
  } catch { return null }
}
export function clearPending() { try { sessionStorage.removeItem(PENDING_KEY) } catch { /* noop */ } }

export async function stakeIn(accountId: string, marketId: string): Promise<string> {
  const r = await api.positions(accountId)
  return r.data.find((p) => p.market_id === marketId)?.total_stake ?? '0'
}

/** Polls the contract (via S6) until the account's stake in the market rises above `before`. */
export async function waitForStakeIncrease(accountId: string, marketId: string, before: string, tries = 10, intervalMs = 3000): Promise<string | null> {
  for (let i = 0; i < tries; i++) {
    try {
      const now = await stakeIn(accountId, marketId)
      if (BigInt(now) > BigInt(before)) return now
    } catch { /* transient; keep polling */ }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  return null
}

/** Reads and strips wallet redirect params (?transactionHashes= / ?errorCode=). */
export function consumeRedirectParams(): { hashes: string[]; error: string | null } | null {
  const u = new URL(window.location.href)
  const hashes = u.searchParams.get('transactionHashes')
  const error = u.searchParams.get('errorCode')
  if (!hashes && !error) return null
  for (const k of ['transactionHashes', 'errorCode', 'errorMessage']) u.searchParams.delete(k)
  window.history.replaceState(null, '', u.toString())
  return { hashes: hashes ? hashes.split(',') : [], error }
}
