import type {
  ApiErrorBody, Brief, EntryIntent, Envelope, FundingTokens, MainnetFundingDiscovery, Market, MarketDetail, MarketEvidence,
  FundingQuoteResult, FundingStatusResult, PoolSnapshot, Position, PulseData, PulseWindow, QuoteRequest, Readiness, ResearchCouncil, ScoutCandidate, ScoutDirection, ScoutMeta, Trend, WalletBalances,
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
  marketResearch: (id: string) => request<{ brief: Brief; market: Market }>(`/api/markets/${enc(id)}/research`, { method: 'POST', body: '{}' }),
  marketCouncil: (id: string, body: { allow_ai?: boolean; force?: boolean } = {}) =>
    request<{ council: ResearchCouncil; market: Market }>(`/api/markets/${enc(id)}/council`, { method: 'POST', body: JSON.stringify(body) }),
  marketCouncilLatest: (id: string) => request<{ council: ResearchCouncil; market: Market }>(`/api/markets/${enc(id)}/council`),
  trends: () => request<Trend[], { count: number }>('/api/trends'),
  scout: (direction: ScoutDirection = 'all', limit = 12) =>
    request<ScoutCandidate[], ScoutMeta>(`/api/scout?direction=${direction}&limit=${limit}`),
  scoutDetail: (id: string) => request<ScoutCandidate>(`/api/scout/${enc(id)}`),
  pulse: (window: PulseWindow = '7d', refresh = true) =>
    request<PulseData>(`/api/pulse?window=${window}&refresh=${refresh ? 'true' : 'false'}`),
  readiness: (accountId: string) => request<Readiness>(`/api/funding/readiness?account_id=${enc(accountId)}`),
  entryIntent: (id: string, body: { account_id: string; side: number | string; stake: string }) =>
    request<EntryIntent>(`/api/markets/${enc(id)}/entry-intent`, { method: 'POST', body: JSON.stringify(body) }),
  marketHistory: (id: string) => request<PoolSnapshot[], { count: number; source: string; recording: boolean }>(`/api/markets/${enc(id)}/history`),
  balances: (accountId: string) => request<WalletBalances>(`/api/wallets/${enc(accountId)}/balances`),
  positions: (accountId: string) => request<Position[]>(`/api/wallets/${enc(accountId)}/positions`),
  fundingTokens: () => request<FundingTokens>('/api/funding/tokens'),
  fundingMainnetTokens: () => request<MainnetFundingDiscovery>('/api/funding/mainnet/tokens'),
  fundingQuote: (body: QuoteRequest) => request<FundingQuoteResult>('/api/funding/quote', { method: 'POST', body: JSON.stringify(body) }),
  fundingMainnetQuote: (body: QuoteRequest & { destination_asset?: string; dry: true }) =>
    request<FundingQuoteResult>('/api/funding/mainnet/quote', { method: 'POST', body: JSON.stringify(body) }),
  fundingLiveQuote: (body: QuoteRequest & { confirm_live_quote: true; confirm_testnet: true }) =>
    request<FundingQuoteResult>('/api/funding/live-quote', { method: 'POST', body: JSON.stringify(body) }),
  fundingDeposit: (body: { quote_id: string; tx_hash: string; submit: true; user_confirmed: true }) =>
    request<FundingStatusResult>('/api/funding/deposit', { method: 'POST', body: JSON.stringify(body) }),
  fundingStatus: (quoteId: string, refresh = false) =>
    request<FundingStatusResult>(`/api/funding/status/${enc(quoteId)}${refresh ? '?refresh=true' : ''}`),
}
