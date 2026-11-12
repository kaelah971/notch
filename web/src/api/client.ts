import type {
  ApiErrorBody, Brief, EntryIntent, Envelope, FundingInstructions, FundingQuote, FundingTokens, Market, MarketDetail, MarketEvidence,
  Position, QuoteRequest, Readiness, Trend, WalletBalances,
} from './types'

const BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request<T, M = Record<string, unknown>>(path: string, init?: RequestInit): Promise<Envelope<T, M>> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(0, 'NETWORK', 'The Notch API is unreachable.')
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const e = (body as ApiErrorBody | null)?.error
    throw new ApiError(res.status, e?.code ?? `HTTP_${res.status}`, e?.message ?? res.statusText, e?.details)
  }
  return body as Envelope<T, M>
}

const enc = encodeURIComponent

export const api = {
  health: () => request<{ status: string; network: string; checks: Record<string, unknown> }>('/api/health'),
  markets: () => request<Market[], { count: number; network: string }>('/api/markets'),
  market: (id: string) => request<MarketDetail>(`/api/markets/${enc(id)}`),
  marketEvidence: (id: string) => request<MarketEvidence>(`/api/markets/${enc(id)}/evidence`),
  marketBrief: (id: string) => request<{ brief: Brief; market: Market }>(`/api/markets/${enc(id)}/brief`),
  trends: () => request<Trend[], { count: number }>('/api/trends'),
  readiness: (accountId: string) => request<Readiness>(`/api/funding/readiness?account_id=${enc(accountId)}`),
  entryIntent: (id: string, body: { account_id: string; side: number | string; stake: string }) =>
    request<EntryIntent>(`/api/markets/${enc(id)}/entry-intent`, { method: 'POST', body: JSON.stringify(body) }),
  balances: (accountId: string) => request<WalletBalances>(`/api/wallets/${enc(accountId)}/balances`),
  positions: (accountId: string) => request<Position[]>(`/api/wallets/${enc(accountId)}/positions`),
  fundingTokens: () => request<FundingTokens>('/api/funding/tokens'),
  fundingQuote: (body: QuoteRequest) => request<{ quote: FundingQuote; instructions?: FundingInstructions }>('/api/funding/quote', { method: 'POST', body: JSON.stringify(body) }),
  fundingStatus: (quoteId: string, refresh = false) =>
    request<{ quote: FundingQuote; [k: string]: unknown }>(`/api/funding/status/${enc(quoteId)}${refresh ? '?refresh=true' : ''}`),
}
