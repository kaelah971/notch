import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useApi } from '../api/useApi'
import type { FundingQuoteResult } from '../api/types'
import { formatUnits, formatUtc, parseUnits, relativeTo } from '../api/format'

const CHAIN_LABELS: Record<string, string> = {
  base: 'Base Sepolia',
  arb: 'Arbitrum Sepolia',
  eth: 'Ethereum Sepolia',
  bsc: 'BSC Testnet',
  aurora: 'Aurora Testnet',
  sol: 'Solana devnet',
  stellar: 'Stellar testnet',
  sui: 'Sui testnet',
  xrp: 'XRP Ledger testnet',
  btc: 'Bitcoin testnet4',
  hypercore: 'Hypercore testnet',
}

const chainLabel = (chain: string) => CHAIN_LABELS[chain] ?? `${chain} testnet`
const inputHint = (chain: string) => {
  if (['base', 'arb', 'eth', 'bsc', 'aurora', 'hypercore'].includes(chain)) return '0x… EVM address'
  if (chain === 'sol') return 'Solana devnet address'
  if (chain === 'stellar') return 'G… Stellar address'
  if (chain === 'sui') return '0x… Sui address'
  if (chain === 'xrp') return 'r… XRP testnet address'
  if (chain === 'btc') return 'tb1… Bitcoin testnet address'
  return 'Refund address on the source chain'
}

interface StoredQuote { key: string; result: FundingQuoteResult }

/** Read-only Tidepool discovery and dry-quote flow. Phase 7B deposit actions are intentionally absent. */
export function Funding({ accountId }: { accountId: string }) {
  const [tokens] = useApi(() => api.fundingTokens().then((response) => response.data), [])
  const [chain, setChain] = useState('')
  const [sourceAsset, setSourceAsset] = useState('')
  const [amount, setAmount] = useState('')
  const [refundTo, setRefundTo] = useState('')
  const [storedQuote, setStoredQuote] = useState<StoredQuote | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const data = tokens.status === 'ok' ? tokens.data : null
  const activeChain = chain || data?.source_chains[0] || ''
  const sourceTokens = useMemo(
    () => data?.tokens.filter((token) => token.blockchain === activeChain && token.asset_id !== data.destination_asset) ?? [],
    [data, activeChain],
  )
  const activeAsset = sourceTokens.find((token) => token.asset_id === sourceAsset) ?? sourceTokens[0] ?? null
  const rawAmount = activeAsset ? parseUnits(amount, activeAsset.decimals) : null
  const quoteKey = `${activeAsset?.asset_id ?? ''}|${amount}|${refundTo.trim()}|${accountId}`
  const quote = storedQuote?.key === quoteKey ? storedQuote.result : null
  const canQuote = !!activeAsset && !!rawAmount && !!refundTo.trim() && !busy

  function chooseChain(next: string) {
    setChain(next)
    setSourceAsset('')
    setStoredQuote(null)
    setError(null)
  }

  function chooseAsset(next: string) {
    setSourceAsset(next)
    setStoredQuote(null)
    setError(null)
  }

  async function requestDryQuote() {
    if (!activeAsset || !rawAmount || !refundTo.trim()) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.fundingQuote({
        source_asset: activeAsset.asset_id,
        source_chain: activeAsset.blockchain,
        amount: rawAmount,
        recipient: accountId,
        refund_to: refundTo.trim(),
        deposit_type: 'ORIGIN_CHAIN',
        slippage_bps: 100,
        deadline_minutes: 30,
        dry: true,
      })
      setStoredQuote({ key: quoteKey, result: result.data })
    } catch (reason) {
      setError(reason instanceof ApiError ? `${reason.code}: ${reason.message}` : reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  if (tokens.status === 'loading') return <div className="skeleton" style={{ height: 260 }} />
  if (tokens.status === 'error') return <p className="dim">Funding discovery is unavailable right now. The provider reason is not available.</p>
  if (!data || data.source_chains.length === 0 || sourceTokens.length === 0) {
    return <p className="dim">No external testnet funding route is currently offered to the NEAR Testnet collateral.</p>
  }

  const providerQuote = quote?.provider_quote.quote
  const q = quote?.quote
  const validation = quote?.validation
  const invalidAmount = amount.trim() !== '' && !rawAmount

  return (
    <div className="card fund" aria-label="Fund Notch Wallet">
      <div className="fund-intro">
        <div>
          <p className="eyebrow">Read-only discovery · 1Click-compatible</p>
          <h3>Fund Notch Wallet</h3>
          <p className="dim">Discover a supported external testnet route into your connected NEAR Testnet wallet. This requests a genuine dry quote only.</p>
        </div>
        <span className="badge">TESTNET ONLY</span>
      </div>

      <div className="fund-boundary" role="note">
        <strong>{data.network}</strong>
        <span>{data.provider}. Test tokens have no monetary value. A dry quote does not move funds, create a deposit address, or authorize a wallet.</span>
      </div>

      <div className="fund-row fund-row-three">
        <label className="field" style={{ marginTop: 0 }}>
          <span>Source testnet</span>
          <select className="field-in sel" value={activeChain} onChange={(event) => chooseChain(event.target.value)}>
            {data.source_chains.map((item) => <option key={item} value={item}>{chainLabel(item)}</option>)}
          </select>
        </label>
        <label className="field" style={{ marginTop: 0 }}>
          <span>Token</span>
          <select className="field-in sel" value={activeAsset?.asset_id ?? ''} onChange={(event) => chooseAsset(event.target.value)}>
            {sourceTokens.map((token) => <option key={token.asset_id} value={token.asset_id}>{token.symbol} · {token.decimals} decimals</option>)}
          </select>
        </label>
        <label className="field" style={{ marginTop: 0 }}>
          <span>Amount</span>
          <div className="field-in" data-invalid={invalidAmount || undefined}>
            <input inputMode="decimal" placeholder="0.0" value={amount} aria-invalid={invalidAmount || undefined} onChange={(event) => { setAmount(event.target.value.replace(/[^\d.]/g, '')); setStoredQuote(null) }} />
            <span className="dim">{activeAsset?.symbol}</span>
          </div>
          {invalidAmount && <small className="err">Use up to {activeAsset?.decimals} decimal places.</small>}
        </label>
      </div>

      <div className="fund-destination-grid">
        <div className="fund-destination">
          <span className="field-label">Destination wallet</span>
          <strong className="mono">{accountId}</strong>
          <small>NEAR Testnet · {data.destination_asset}</small>
        </div>
        <label className="field" style={{ marginTop: 0 }}>
          <span>Refund destination on {chainLabel(activeChain)}</span>
          <input className="field-in fund-refund" value={refundTo} placeholder={inputHint(activeChain)} aria-describedby="fund-refund-help" onChange={(event) => { setRefundTo(event.target.value); setStoredQuote(null) }} />
          <small id="fund-refund-help">Required and validated by the server for the selected source chain. Use an address you control.</small>
        </label>
      </div>

      <div className="fund-review-line">
        <span>Route: <strong>{activeAsset?.symbol} · {chainLabel(activeChain)}</strong> → <strong>test-USDC · NEAR Testnet</strong></span>
        <span>Slippage cap: <strong>1%</strong> · Quote window: <strong>30 min</strong></span>
      </div>

      <div className="row-gap fund-actions">
        <button className="btn btn-primary" onClick={requestDryQuote} disabled={!canQuote}>{busy ? 'Requesting dry quote…' : 'Inspect genuine dry quote'}</button>
        <a className="btn btn-quiet" href="https://www.usetidepool.tech/docs/quickstart" target="_blank" rel="noreferrer">Provider docs <span aria-hidden="true">↗</span></a>
      </div>

      {error && <p className="fine err" role="alert">{error}</p>}

      {quote && q && providerQuote && validation && (
        <section className="fund-quote" aria-labelledby="fund-quote-heading" aria-live="polite">
          <div className="fund-quote-head">
            <div>
              <p className="eyebrow">Genuine provider response · dry=true</p>
              <h4 id="fund-quote-heading">Quote is available</h4>
            </div>
            <span className="badge badge-replay">NO TRANSFER</span>
          </div>
          <div className="fund-quote-grid">
            <div><span>You would send</span><strong className="mono">{formatUnits(q.amount_in, q.source_decimals, 8)} {q.source_symbol}</strong><small>{providerQuote.amount_in_formatted} source units · {providerQuote.amount_in_usd} USD estimate</small></div>
            <div><span>Estimated output</span><strong className="mono">{formatUnits(q.amount_out, q.destination_decimals, 8)} {q.destination_symbol}</strong><small>{providerQuote.amount_out_formatted} destination units · {providerQuote.amount_out_usd} USD estimate</small></div>
            <div><span>Minimum output</span><strong className="mono">{formatUnits(q.min_amount_out, q.destination_decimals, 8)} {q.destination_symbol}</strong><small>After {((q.slippage_bps ?? 100) / 100).toFixed(2)}% configured slippage</small></div>
            <div><span>Estimated time</span><strong>{providerQuote.time_estimate}s</strong><small>Returned by provider</small></div>
          </div>
          <dl className="kv kv-tight fund-quote-meta">
            <div><dt>Supported route</dt><dd>{validation.route.label}</dd></div>
            <div><dt>Recipient</dt><dd className="mono hash">{q.recipient}</dd></div>
            <div><dt>Refund destination</dt><dd className="mono hash">{q.refund_to}</dd></div>
            <div><dt>Provider</dt><dd>Tidepool · community-operated testnet sandbox</dd></div>
            <div><dt>Quote timestamp</dt><dd>{q.quote_timestamp ? formatUtc(q.quote_timestamp) : '—'}</dd></div>
            <div><dt>Freshness</dt><dd>{q.expires_at ? `${relativeTo(q.expires_at)} · expires ${formatUtc(q.expires_at)}` : 'No expiry returned'}</dd></div>
            <div><dt>Provider fee fields</dt><dd>{providerQuote.withdraw_fee || providerQuote.refund_fee ? `withdraw ${providerQuote.withdraw_fee ?? '—'} · refund ${providerQuote.refund_fee ?? '—'} base units` : `No explicit fee fields · implied spread ${validation.implied_fee_usd} USD estimate`}</dd></div>
          </dl>
          <p className="fund-warning" role="note">This quote has not funded the wallet. No deposit address was returned, no transaction was signed, and no swap was executed. Future deposits may require source-chain gas.</p>
          <Link className="btn btn-quiet" to="/app/markets?f=open">Continue to open prediction markets <span aria-hidden="true">→</span></Link>
        </section>
      )}
    </div>
  )
}
