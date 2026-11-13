import { RefreshCw, ExternalLink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { formatUnits, formatUtc, relativeTo } from '../api/format'
import type { Market, PulseWindow } from '../api/types'
import { useApi } from '../api/useApi'
import { ErrorState, SkeletonList } from '../components/States'
import { explorerAccount, explorerTx } from '../wallet/WalletProvider'
import { FOLLOWING_CHANGED, getFollowing } from '../signals/follows'
import { ParticipantDirectory } from '../signals/Discovery'
import './Pulse.css'

const WINDOWS: { value: PulseWindow; label: string }[] = [
  { value: '24h', label: '24 hours' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: 'all', label: 'Since tracking began' },
]

const shortId = (value: string) => value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value
const marketName = (marketId: string, markets: Market[]) => {
  const market = markets.find((item) => item.market_id === marketId)
  if (!market) return marketId
  const prefix = market.question.replace(/^(HISTORICAL REPLAY \(not a forecast\)|FORECAST \(not a replay\)):\s*/i, '')
  return prefix.length > 72 ? `${prefix.slice(0, 69)}…` : prefix
}

type FeedView = 'everyone' | 'following'

export function Pulse({ markets = [] }: { markets?: Market[] }) {
  const [period, setPeriod] = useState<PulseWindow>('7d')
  const [feedView, setFeedView] = useState<FeedView>('everyone')
  const [following, setFollowing] = useState<string[]>(getFollowing)
  const [state, reload] = useApi(() => api.pulse(period), [period])
  useEffect(() => {
    const refreshFollowing = () => setFollowing(getFollowing())
    window.addEventListener(FOLLOWING_CHANGED, refreshFollowing)
    return () => window.removeEventListener(FOLLOWING_CHANGED, refreshFollowing)
  }, [])

  return (
    <section className="pulse" aria-labelledby="pulse-title">
      <div className="pulse-head">
        <div>
          <p className="eyebrow">Onchain activity</p>
          <h2 id="pulse-title">Notch Pulse</h2>
          <p>Confirmed entries from the market contract, not attention scores or inferred wallet activity.</p>
        </div>
        <div className="pulse-controls">
          <label className="pulse-window">
            <span className="visually-hidden">Pulse time window</span>
            <select value={period} onChange={(event) => setPeriod(event.target.value as PulseWindow)}>
              {WINDOWS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <button type="button" className="pulse-refresh" onClick={reload} aria-label="Refresh Pulse" title="Refresh Pulse">
            <RefreshCw size={16} aria-hidden />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {state.status === 'loading' && <SkeletonList n={2} h={84} />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={reload} />}
      {state.status === 'ok' && <PulseContent data={state.data.data} markets={markets} feedView={feedView} following={following} onFeedViewChange={setFeedView} />}
    </section>
  )
}

function PulseContent({ data, markets, feedView, following, onFeedViewChange }: { data: NonNullable<Awaited<ReturnType<typeof api.pulse>>>['data']; markets: Market[]; feedView: FeedView; following: string[]; onFeedViewChange: (view: FeedView) => void }) {
  const { coverage, metrics, hot_markets: hotMarkets, participants, recent_calls: recentCalls } = data
  const visibleCalls = feedView === 'following' ? recentCalls.filter((call) => following.includes(call.account_id)) : recentCalls
  const visibleParticipants = feedView === 'following' ? participants.filter((participant) => following.includes(participant.account_id)) : participants
  const amount = (value: string) => formatUnits(value, data.currency.decimals, 2)
  const coverageText = coverage.status === 'tracking'
    ? `Finalized event coverage from block ${coverage.start_block_height?.toLocaleString('en-US') ?? '—'}.`
    : coverage.status === 'degraded'
      ? 'The last durable snapshot is shown; the indexer could not advance.'
      : coverage.status === 'not_configured'
        ? 'Pulse indexing is not configured for this API process.'
        : 'Pulse has not established a finalized tracking boundary yet.'

  return (
    <>
      <div className={`pulse-coverage pulse-coverage-${coverage.status}`} role="status">
        <span className="pulse-signal" aria-hidden />
        <div>
          <strong>{coverage.available ? 'Verified coverage' : 'Coverage is limited'}</strong>
          <p>{coverageText} {coverage.scope}.</p>
          {coverage.last_error && <p className="pulse-error">Last refresh: {coverage.last_error}</p>}
        </div>
      </div>

      <div className="pulse-metrics" aria-label="Pulse metrics">
        <Metric label="Forecasters" value={metrics.forecaster_count.toLocaleString('en-US')} note={`in ${data.window}`} />
        <Metric label="New observers" value={metrics.new_forecaster_count.toLocaleString('en-US')} note="first observed here" />
        <Metric label="Confirmed volume" value={`${amount(metrics.confirmed_volume_base_units)} ${data.currency.symbol}`} note="accepted entries" />
        <Metric label="Successful positions" value={metrics.successful_entries.toLocaleString('en-US')} note="unique markets" />
      </div>

      <div className="pulse-grid">
        <section className="pulse-panel" aria-labelledby="pulse-hot-title">
          <div className="pulse-panel-head">
            <div><p className="eyebrow">Where activity clusters</p><h3 id="pulse-hot-title">Hot markets</h3></div>
            <span className="pulse-panel-note">by confirmed volume</span>
          </div>
          {hotMarkets.length === 0
            ? <EmptyPulse text="No indexed market activity in this window." />
            : <ol className="pulse-hot-list">
              {hotMarkets.map((market, index) => (
                <li key={market.market_id}>
                  <span className="pulse-rank mono">{index + 1}</span>
                  <div className="pulse-market-copy">
                    <strong title={market.market_id}>{marketName(market.market_id, markets)}</strong>
                    <span className="pulse-subline mono">{market.market_id} · {market.forecaster_count} forecaster{market.forecaster_count === 1 ? '' : 's'}</span>
                  </div>
                  <span className="pulse-value mono">{amount(market.confirmed_volume_base_units)} <small>{data.currency.symbol}</small></span>
                </li>
              ))}
            </ol>}
        </section>

        <section className="pulse-panel" aria-labelledby="pulse-calls-title">
          <div className="pulse-panel-head">
            <div><p className="eyebrow">Receipt-backed feed</p><h3 id="pulse-calls-title">Recent calls</h3></div>
            <span className="pulse-panel-note">finalized only</span>
          </div>
          <div className="pulse-feed-tabs" role="tablist" aria-label="Pulse feed audience">
            <button type="button" role="tab" aria-selected={feedView === 'everyone'} className={feedView === 'everyone' ? 'is-active' : ''} onClick={() => onFeedViewChange('everyone')}>Everyone</button>
            <button type="button" role="tab" aria-selected={feedView === 'following'} className={feedView === 'following' ? 'is-active' : ''} onClick={() => onFeedViewChange('following')}>Following</button>
          </div>
          <p className="pulse-feed-note">Following is saved on this device only. It never creates a server-side follower count.</p>
          {visibleCalls.length === 0
            ? <EmptyPulse text={feedView === 'following' ? 'No calls from your followed accounts are indexed in this window.' : 'No successful calls are indexed in this window. This is not proof that no one called.'} />
            : <ul className="pulse-call-list">
              {visibleCalls.map((call) => (
                <li key={call.event_id}>
                  <div className="pulse-call-top">
                    <Link className="pulse-account" to={`/app/p/${encodeURIComponent(call.account_id)}`} title={`Open ${call.account_id} Signals profile`}>
                      {shortId(call.account_id)}
                    </Link>
                    <a className="pulse-account pulse-account-explorer" href={explorerAccount(call.account_id)} target="_blank" rel="noreferrer" aria-label={`Open ${call.account_id} on NEAR Explorer`} title="Open account on NEAR Explorer">
                      <ExternalLink size={12} aria-hidden />
                    </a>
                    <time dateTime={call.observed_at_utc} title={formatUtc(call.observed_at_utc)}>{relativeTo(call.observed_at_utc)}</time>
                  </div>
                  <p className="pulse-call-market" title={call.market_id}>{marketName(call.market_id, markets)}</p>
                  <div className="pulse-call-bottom">
                    <span className="mono">outcome {call.outcome} · {amount(call.amount_base_units)} {data.currency.symbol}</span>
                    <a className="pulse-tx" href={explorerTx(call.tx_hash)} target="_blank" rel="noreferrer">tx {shortId(call.tx_hash)} <ExternalLink size={12} aria-hidden /></a>
                  </div>
                </li>
              ))}
            </ul>}
        </section>
      </div>

      <ParticipantDirectory participants={visibleParticipants} markets={markets} />

      <p className="pulse-footnote">Accounts and calls are public Testnet records. Amounts are test-USDC base-unit sums from accepted <code>position_entered</code> receipts; repeated entries in one market count once as a position, while the volume remains the confirmed sum of accepted events. These are not forecasts, odds, profit, or real-world volume.</p>
    </>
  )
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="pulse-metric"><span>{label}</span><strong className="mono">{value}</strong><small>{note}</small></div>
}

function EmptyPulse({ text }: { text: string }) {
  return <div className="pulse-empty"><strong>No data yet</strong><p>{text}</p></div>
}
