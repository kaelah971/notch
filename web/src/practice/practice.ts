import type { Market, PredictionStatus } from '../api/types'

export const PRACTICE_STORAGE_KEY = 'notch.practice.arena.v1'
export const PRACTICE_STARTING_CREDITS = 1_000

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

export interface PracticePosition {
  market_id: string
  market_question: string
  choice_index: number
  choice: string
  stake: number
  created_at_utc: string
}

export interface PracticeState {
  version: 1
  positions: PracticePosition[]
}

export interface PracticeLedgerPosition extends PracticePosition {
  market: Market | null
  status: PredictionStatus
  outcome: string | null
}

export interface PracticeLedger {
  positions: PracticeLedgerPosition[]
  available_credits: number
  reserved_credits: number
}

export interface PracticeSummary {
  total: number
  correct: number
  incorrect: number
  pending: number
  voided: number
  unknown: number
  completed: number
  accuracy: number | null
  current_streak: number
  best_streak: number
}

export type PracticeValidationCode =
  | 'INVALID_CHOICE'
  | 'INVALID_STAKE'
  | 'MARKET_CLOSED'
  | 'DUPLICATE_MARKET'
  | 'INSUFFICIENT_CREDITS'

export type PracticeValidation = { ok: true } | { ok: false; code: PracticeValidationCode }

function browserStorage(): StorageLike | null {
  if (typeof window === 'undefined') return null
  try { return window.localStorage } catch { return null }
}

export function emptyPracticeState(): PracticeState {
  return { version: 1, positions: [] }
}

export function normalizePracticeState(value: unknown): PracticeState {
  if (!value || typeof value !== 'object') return emptyPracticeState()
  const raw = value as { positions?: unknown }
  if (!Array.isArray(raw.positions)) return emptyPracticeState()
  const seen = new Set<string>()
  const positions: PracticePosition[] = []
  for (const item of raw.positions) {
    if (!item || typeof item !== 'object') continue
    const row = item as Partial<PracticePosition>
    if (typeof row.market_id !== 'string' || !row.market_id || seen.has(row.market_id)) continue
    if (typeof row.market_question !== 'string' || typeof row.choice !== 'string') continue
    const choiceIndex = row.choice_index
    const stake = row.stake
    if (typeof choiceIndex !== 'number' || !Number.isSafeInteger(choiceIndex) || choiceIndex < 0) continue
    if (typeof stake !== 'number' || !Number.isSafeInteger(stake) || stake <= 0) continue
    if (typeof row.created_at_utc !== 'string' || !row.created_at_utc) continue
    seen.add(row.market_id)
    positions.push({
      market_id: row.market_id,
      market_question: row.market_question,
      choice_index: choiceIndex,
      choice: row.choice,
      stake,
      created_at_utc: row.created_at_utc,
    })
  }
  return { version: 1, positions }
}

export function readPracticeState(storage: StorageLike | null = browserStorage()): PracticeState {
  if (!storage) return emptyPracticeState()
  try { return normalizePracticeState(JSON.parse(storage.getItem(PRACTICE_STORAGE_KEY) ?? 'null')) } catch { return emptyPracticeState() }
}

export function writePracticeState(state: PracticeState, storage: StorageLike | null = browserStorage()): boolean {
  if (!storage) return false
  try {
    storage.setItem(PRACTICE_STORAGE_KEY, JSON.stringify(normalizePracticeState(state)))
    return true
  } catch { return false }
}

export function isFinalizedMarket(market: Market): boolean {
  return market.status === 'resolved' || market.status === 'voided'
}

export function isPracticeReplay(market: Market): boolean {
  return market.is_historical_replay && isFinalizedMarket(market)
}

export function isPracticeSelectable(market: Market, now = Date.now()): boolean {
  if (isPracticeReplay(market)) return true
  if (market.status !== 'open' || market.display_status !== 'open_future' || !market.entries_open || market.entries_paused) return false
  const deadline = Date.parse(market.close_at_utc)
  return Number.isFinite(deadline) && deadline > now
}

export function classifyPracticePosition(position: Pick<PracticePosition, 'choice_index'>, market: Market | null): PredictionStatus {
  if (!market) return 'UNKNOWN'
  if (market.status === 'voided' || market.resolution_kind === 'void' || market.resolution_kind === 'tie' || market.display_status === 'voided') return 'VOIDED'
  if (market.status === 'open' || market.status === 'closed') return 'PENDING'
  if (market.status !== 'resolved') return 'UNKNOWN'
  if (market.evidence_available !== true || market.resolution_kind !== 'winning_outcome') return 'UNKNOWN'
  const winner = market.winning_outcome
  if (!Number.isInteger(winner) || winner == null || winner < 0 || winner >= market.choices.length) return 'UNKNOWN'
  if (!Number.isInteger(position.choice_index) || position.choice_index < 0 || position.choice_index >= market.choices.length) return 'UNKNOWN'
  return position.choice_index === winner ? 'CORRECT' : 'INCORRECT'
}

export function getPracticeLedger(state: PracticeState, markets: Market[]): PracticeLedger {
  const byId = new Map(markets.map((market) => [market.market_id, market]))
  const positions = state.positions.map((position): PracticeLedgerPosition => {
    const market = byId.get(position.market_id) ?? null
    const status = classifyPracticePosition(position, market)
    return { ...position, market, status, outcome: status === 'CORRECT' || status === 'INCORRECT' ? market?.winning_choice ?? null : null }
  })
  const totalStaked = positions.reduce((sum, position) => sum + position.stake, 0)
  const released = positions.reduce((sum, position) => {
    if (position.status === 'CORRECT') return sum + position.stake * 2
    if (position.status === 'VOIDED') return sum + position.stake
    return sum
  }, 0)
  const reserved = positions.reduce((sum, position) => position.status === 'PENDING' || position.status === 'UNKNOWN' ? sum + position.stake : sum, 0)
  return {
    positions,
    available_credits: Math.max(0, PRACTICE_STARTING_CREDITS - totalStaked + released),
    reserved_credits: reserved,
  }
}

export function summarizePractice(positions: ReadonlyArray<Pick<PracticeLedgerPosition, 'status' | 'created_at_utc'>>): PracticeSummary {
  const counts = { total: positions.length, correct: 0, incorrect: 0, pending: 0, voided: 0, unknown: 0 }
  for (const position of positions) {
    if (position.status === 'CORRECT') counts.correct += 1
    else if (position.status === 'INCORRECT') counts.incorrect += 1
    else if (position.status === 'PENDING') counts.pending += 1
    else if (position.status === 'VOIDED') counts.voided += 1
    else counts.unknown += 1
  }
  const ordered = [...positions].sort((a, b) => Date.parse(a.created_at_utc) - Date.parse(b.created_at_utc))
  let best = 0
  let run = 0
  for (const position of ordered) {
    if (position.status === 'CORRECT') { run += 1; best = Math.max(best, run) } else run = 0
  }
  const recent = [...ordered].reverse()
  let current = 0
  for (const position of recent) {
    if (position.status !== 'CORRECT') break
    current += 1
  }
  const completed = counts.correct + counts.incorrect
  return {
    ...counts,
    completed,
    accuracy: completed ? counts.correct / completed * 100 : null,
    current_streak: current,
    best_streak: best,
  }
}

export function validatePracticeEntry(market: Market, state: PracticeState, choiceIndex: number, stake: number, ledger: PracticeLedger, now = Date.now()): PracticeValidation {
  if (!Number.isInteger(choiceIndex) || choiceIndex < 0 || choiceIndex >= market.choices.length) return { ok: false, code: 'INVALID_CHOICE' }
  if (!Number.isSafeInteger(stake) || stake <= 0) return { ok: false, code: 'INVALID_STAKE' }
  if (!isPracticeSelectable(market, now)) return { ok: false, code: 'MARKET_CLOSED' }
  if (state.positions.some((position) => position.market_id === market.market_id)) return { ok: false, code: 'DUPLICATE_MARKET' }
  if (stake > ledger.available_credits) return { ok: false, code: 'INSUFFICIENT_CREDITS' }
  return { ok: true }
}

export function addPracticePosition(state: PracticeState, market: Market, choiceIndex: number, stake: number, markets: Market[], now = Date.now()): { state: PracticeState; validation: PracticeValidation } {
  const ledger = getPracticeLedger(state, markets)
  const validation = validatePracticeEntry(market, state, choiceIndex, stake, ledger, now)
  if (!validation.ok) return { state, validation }
  const next: PracticePosition = {
    market_id: market.market_id,
    market_question: market.question,
    choice_index: choiceIndex,
    choice: market.choices[choiceIndex],
    stake,
    created_at_utc: new Date(now).toISOString(),
  }
  return { state: { version: 1, positions: [...state.positions, next] }, validation }
}
