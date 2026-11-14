import type {
  ApiErrorBody, Brief, EntryIntent, Envelope, FundingTokens, MainnetFundingDiscovery, Market, MarketDetail, MarketEvidence,
  CreatorIdentitySession, CreatorNoteChallenge, CreatorPaymentIntent, CreatorPremiumContent, CreatorPurchases, CreatorPayoutStatus, CreatorResearchNote, CreatorNotesMeta, CreatorSubscription, CreatorSubscriptionPlan, CreatorSubscriptions, FundingQuoteResult, FundingStatusResult, Notification, NotificationMeta, PoolSnapshot, Position, PrivateResearchRecord, PulseData, PulseWindow, QuoteRequest, Readiness, ResearchCouncil, ScoutCandidate, ScoutDirection, ScoutMeta, Trend, WalletBalances,
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
    const headers = new Headers(init?.headers)
    headers.set('Accept', 'application/json')
    headers.set('Content-Type', 'application/json')
    res = await fetch(`${BASE}${path}`, { ...init, headers })
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
const bearer = (token: string): HeadersInit => ({ Authorization: `Bearer ${token}` })

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
  notifications: (token: string, limit = 50) => request<Notification[], NotificationMeta>(`/api/notifications?limit=${limit}`, { headers: bearer(token) }),
  notificationRead: (token: string, notificationId: string) => request<{ notification_id: string; read: boolean }>(`/api/notifications/${enc(notificationId)}/read`, { method: 'POST', headers: bearer(token), body: '{}' }),
  notificationsReadAll: (token: string) => request<{ marked_read: number }>('/api/notifications/read-all', { method: 'POST', headers: bearer(token), body: '{}' }),
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
  creatorChallenge: (accountId: string) =>
    request<CreatorNoteChallenge>('/api/research/identity/challenge', { method: 'POST', body: JSON.stringify({ account_id: accountId }) }),
  creatorVerify: (body: { challenge_id: string; account_id: string; public_key: string; signature: string }) =>
    request<CreatorIdentitySession>('/api/research/identity/verify', { method: 'POST', body: JSON.stringify(body) }),
  creatorRevoke: (token: string) => request<{ revoked: boolean; account_id: string; revoked_at: string }>('/api/research/identity/revoke', { method: 'POST', headers: bearer(token), body: '{}' }),
  creatorMe: (token: string) => request<{ account_id: string; public_key: string; expires_at: string; network?: string; verified: boolean }>('/api/research/me', { headers: bearer(token) }),
  creatorPayout: (token: string) => request<CreatorPayoutStatus>('/api/research/payout', { headers: bearer(token) }),
  creatorConfigurePayout: (token: string, payoutAccount?: string) => request<CreatorPayoutStatus>('/api/research/payout/configure', { method: 'POST', headers: bearer(token), body: JSON.stringify(payoutAccount ? { payout_account: payoutAccount } : {}) }),
  creatorPublicNotes: (limit = 12) => request<CreatorResearchNote[], CreatorNotesMeta>(`/api/research/notes?limit=${limit}`),
  subscriptionPlans: (limit = 20) => request<CreatorSubscriptionPlan[]>(`/api/research/plans?limit=${limit}`),
  subscriptionPlan: (planId: string) => request<CreatorSubscriptionPlan>(`/api/research/plans/${enc(planId)}`),
  creatorPlans: (token: string, limit = 50) => request<CreatorSubscriptionPlan[]>(`/api/research/plans/mine?limit=${limit}`, { headers: bearer(token) }),
  creatorPlansForAccount: (accountId: string, limit = 20) => request<CreatorSubscriptionPlan[], CreatorNotesMeta>(`/api/creators/${enc(accountId)}/plans?limit=${limit}`),
  creatorPlanCreate: (token: string, body: Record<string, unknown>) => request<CreatorSubscriptionPlan>('/api/research/plans', { method: 'POST', headers: bearer(token), body: JSON.stringify(body) }),
  creatorPlanUpdate: (token: string, planId: string, body: Record<string, unknown>) => request<CreatorSubscriptionPlan>(`/api/research/plans/${enc(planId)}/update`, { method: 'POST', headers: bearer(token), body: JSON.stringify(body) }),
  creatorPublicNote: (noteId: string) => request<CreatorResearchNote>(`/api/research/notes/${enc(noteId)}`),
  creatorProfile: (accountId: string, limit = 20) => request<CreatorResearchNote[], CreatorNotesMeta>(`/api/creators/${enc(accountId)}/notes?limit=${limit}`),
  creatorMine: (token: string, limit = 20) => request<CreatorResearchNote[], CreatorNotesMeta>(`/api/research/notes/mine?limit=${limit}`, { headers: bearer(token) }),
  vaultMine: (token: string, limit = 50) => request<PrivateResearchRecord[], CreatorNotesMeta>(`/api/research/vault?limit=${limit}`, { headers: bearer(token) }),
  vaultGet: (token: string, researchId: string) => request<PrivateResearchRecord>(`/api/research/vault/${enc(researchId)}`, { headers: bearer(token) }),
  vaultCreate: (token: string, body: Record<string, unknown>) => request<PrivateResearchRecord>('/api/research/vault', { method: 'POST', headers: bearer(token), body: JSON.stringify(body) }),
  vaultUpdate: (token: string, researchId: string, body: Record<string, unknown>) => request<PrivateResearchRecord>(`/api/research/vault/${enc(researchId)}/update`, { method: 'POST', headers: bearer(token), body: JSON.stringify(body) }),
  vaultDelete: (token: string, researchId: string) => request<{ research_id: string; deleted: boolean; visibility: string }>(`/api/research/vault/${enc(researchId)}/delete`, { method: 'POST', headers: bearer(token), body: '{}' }),
  creatorPurchases: (token: string, limit = 50) => request<CreatorPurchases>(`/api/research/purchases?limit=${limit}`, { headers: bearer(token) }),
  creatorPremium: (noteId: string, token: string, revision?: number) => request<CreatorPremiumContent>(`/api/research/notes/${enc(noteId)}/premium${revision ? `?revision=${revision}` : ''}`, { headers: bearer(token) }),
  creatorCreatePaymentIntent: (token: string, noteId: string) => request<CreatorPaymentIntent>(`/api/research/notes/${enc(noteId)}/payment-intents`, { method: 'POST', headers: bearer(token), body: '{}' }),
  creatorPaymentStatus: (token: string, intentId: string) => request<CreatorPaymentIntent>(`/api/research/payment-intents/${enc(intentId)}`, { headers: bearer(token) }),
  subscriptionCreatePaymentIntent: (token: string, planId: string) => request<CreatorPaymentIntent>(`/api/research/plans/${enc(planId)}/payment-intents`, { method: 'POST', headers: bearer(token), body: '{}' }),
  subscriptions: (token: string, limit = 50) => request<CreatorSubscriptions>(`/api/research/subscriptions?limit=${limit}`, { headers: bearer(token) }),
  subscription: (token: string, subscriptionId: string) => request<CreatorSubscription>(`/api/research/subscriptions/${enc(subscriptionId)}`, { headers: bearer(token) }),
  subscriptionCancel: (token: string, subscriptionId: string) => request<CreatorSubscription>(`/api/research/subscriptions/${enc(subscriptionId)}/cancel`, { method: 'POST', headers: bearer(token), body: '{}' }),
  creatorVerifyPayment: (token: string, intentId: string, txHash: string) => request<CreatorPaymentIntent>(`/api/research/payment-intents/${enc(intentId)}/verify`, { method: 'POST', headers: bearer(token), body: JSON.stringify({ tx_hash: txHash }) }),
  creatorCreate: (token: string, body: Record<string, unknown>) => request<CreatorResearchNote>('/api/research/notes', { method: 'POST', headers: bearer(token), body: JSON.stringify(body) }),
  creatorUpdate: (token: string, noteId: string, body: Record<string, unknown>) => request<CreatorResearchNote>(`/api/research/notes/${enc(noteId)}/update`, { method: 'POST', headers: bearer(token), body: JSON.stringify(body) }),
  creatorPublish: (token: string, noteId: string) => request<CreatorResearchNote>(`/api/research/notes/${enc(noteId)}/publish`, { method: 'POST', headers: bearer(token), body: '{}' }),
  creatorWithdraw: (token: string, noteId: string, reason?: string) => request<CreatorResearchNote>(`/api/research/notes/${enc(noteId)}/withdraw`, { method: 'POST', headers: bearer(token), body: JSON.stringify({ reason }) }),
}
