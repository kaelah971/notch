import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useApi } from '../api/useApi'
import type { FundingQuoteResult, FundingStatusResult } from '../api/types'
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

const FUNDING_STORAGE_KEY = 'notch.funding.v1'
const TERMINAL_STATES = new Set(['SUCCESS', 'REFUNDED', 'FAILED', 'EXPIRED'])
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

interface PersistedFunding {
  accountId: string
  liveResult: FundingQuoteResult
  txHash: string
}

function errorText(reason: unknown) {
  return reason instanceof ApiError
    ? `${reason.code}: ${reason.message}`
    : reason instanceof Error
      ? reason.message
      : String(reason)
}

function explorerTx(hash: string) {
  return `https://sepolia.basescan.org/tx/${encodeURIComponent(hash)}`
}

function statusLabel(status: string | null | undefined) {
  switch (status) {
    case 'PENDING_DEPOSIT': return 'Waiting for your deposit'
    case 'KNOWN_DEPOSIT_TX': return 'Deposit transaction submitted'
    case 'INCOMPLETE_DEPOSIT': return 'Partial deposit detected'
    case 'PROCESSING': return 'Provider processing'
    case 'SUCCESS': return 'Provider reports success'
    case 'REFUNDED': return 'Deposit refunded'
    case 'FAILED': return 'Provider reports failure'
    default: return status || 'Awaiting deposit'
  }
}

/** Base Sepolia manual-deposit funding flow. Notch never signs or broadcasts the source transaction. */
export function Funding({ accountId, onVerified }: { accountId: string; onVerified?: () => void }) {
  const [tokens] = useApi(() => api.fundingTokens().then((response) => response.data), [])
  const [mainnetTokens] = useApi(() => api.fundingMainnetTokens().then((response) => response.data), [])
  const [mainnetSourceAsset, setMainnetSourceAsset] = useState('')
  const [mainnetRecipient, setMainnetRecipient] = useState('')
  const [mainnetAmount, setMainnetAmount] = useState('')
  const [mainnetRefundTo, setMainnetRefundTo] = useState('')
  const [mainnetQuote, setMainnetQuote] = useState<FundingQuoteResult | null>(null)
  const [mainnetBusy, setMainnetBusy] = useState(false)
  const [mainnetError, setMainnetError] = useState<string | null>(null)
  const [chain, setChain] = useState('')
  const [sourceAsset, setSourceAsset] = useState('')
  const [amount, setAmount] = useState('')
  const [refundTo, setRefundTo] = useState('')
  const [dryResult, setDryResult] = useState<FundingQuoteResult | null>(null)
  const [liveResult, setLiveResult] = useState<FundingQuoteResult | null>(null)
  const [status, setStatus] = useState<FundingStatusResult | null>(null)
  const [txHash, setTxHash] = useState('')
  const [liveConfirmed, setLiveConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollCount, setPollCount] = useState(0)
  const [verifiedNotified, setVerifiedNotified] = useState(false)

  const data = tokens.status === 'ok' ? tokens.data : null
  const mainnetData = mainnetTokens.status === 'ok' ? mainnetTokens.data : null
  const mainnetSourceTokens = mainnetData?.source_tokens ?? []
  const mainnetDefaultSourceAsset = mainnetSourceTokens.find((token) => token.blockchain === 'base' && token.symbol === 'USDC') ?? mainnetSourceTokens[0] ?? null
  const mainnetActiveAsset = mainnetSourceTokens.find((token) => token.asset_id === mainnetSourceAsset) ?? mainnetDefaultSourceAsset
  const mainnetRawAmount = mainnetActiveAsset ? parseUnits(mainnetAmount, mainnetActiveAsset.decimals ?? 0) : null
  const mainnetTargetRecipient = mainnetRecipient.trim() || mainnetData?.recipient || ''
  const mainnetCanQuote = !!mainnetData?.quote_enabled && !!mainnetData.destination_asset && !!mainnetTargetRecipient && !!mainnetActiveAsset && !!mainnetRawAmount && !!mainnetRefundTo.trim() && !mainnetBusy
  const activeChain = chain || data?.source_chains[0] || ''
  const sourceTokens = useMemo(
    () => data?.tokens.filter((token) => token.blockchain === activeChain && token.asset_id !== data.destination_asset) ?? [],
    [data, activeChain],
  )
  const activeAsset = sourceTokens.find((token) => token.asset_id === sourceAsset) ?? sourceTokens[0] ?? null
  const rawAmount = activeAsset ? parseUnits(amount, activeAsset.decimals) : null
  const quote = dryResult?.quote
  const invalidAmount = amount.trim() !== '' && !rawAmount
  const txValid = /^0x[0-9a-fA-F]{64}$/.test(txHash.trim())
  const liveQuote = liveResult?.quote
  const liveInstructions = liveResult?.instructions
  const currentStatus = status?.provider_status ?? liveQuote?.state
  const destinationState = status?.destination_verification?.state
  const isTerminal = !!status && TERMINAL_STATES.has(status.state)
  const liveExpired = !!liveQuote?.expires_at && new Date(liveQuote.expires_at).getTime() <= Date.now()
  const canQuote = !!activeAsset && !!rawAmount && !!refundTo.trim() && !busy
  const canLiveQuote = activeChain === 'base' && !!dryResult && !liveExpired && !busy && liveConfirmed
  const canSubmitDeposit = !!liveResult && !!txHash.trim() && txValid && !statusBusy && !isTerminal && !liveExpired

  useEffect(() => {
    if (!accountId || typeof window === 'undefined') return
    const stored = window.localStorage.getItem(FUNDING_STORAGE_KEY)
    if (!stored) return
    try {
      const parsed = JSON.parse(stored) as PersistedFunding
      if (parsed.accountId !== accountId || !parsed.liveResult?.quote?.quote_id) return
      setLiveResult(parsed.liveResult)
      setTxHash(parsed.txHash || '')
      api.fundingStatus(parsed.liveResult.quote.quote_id, true)
        .then((response) => setStatus(response.data))
        .catch(() => undefined)
    } catch {
      window.localStorage.removeItem(FUNDING_STORAGE_KEY)
    }
  }, [accountId])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!liveResult) {
      window.localStorage.removeItem(FUNDING_STORAGE_KEY)
      return
    }
    const persisted: PersistedFunding = { accountId, liveResult, txHash }
    window.localStorage.setItem(FUNDING_STORAGE_KEY, JSON.stringify(persisted))
  }, [accountId, liveResult, txHash])

  useEffect(() => {
    if (!status?.deposit_submitted || isTerminal || pollCount >= 12) return
    const timer = window.setTimeout(async () => {
      try {
        setStatusBusy(true)
        const response = await api.fundingStatus(status.quote_id, true)
        setStatus(response.data)
        setPollCount((count) => count + 1)
      } catch (reason) {
        setError(errorText(reason))
      } finally {
        setStatusBusy(false)
      }
    }, 8000)
    return () => window.clearTimeout(timer)
  }, [status, isTerminal, pollCount])

  useEffect(() => {
    if (destinationState === 'DESTINATION_VERIFIED' && !verifiedNotified) {
      onVerified?.()
      setVerifiedNotified(true)
    }
  }, [destinationState, verifiedNotified, onVerified])

  function chooseChain(next: string) {
    setChain(next)
    setSourceAsset('')
    setDryResult(null)
    setError(null)
  }

  function chooseAsset(next: string) {
    setSourceAsset(next)
    setDryResult(null)
    setError(null)
  }

  async function requestMainnetDryQuote() {
    if (!mainnetData?.destination_asset || !mainnetTargetRecipient || !mainnetActiveAsset || !mainnetRawAmount || !mainnetRefundTo.trim()) return
    setMainnetBusy(true)
    setMainnetError(null)
    setMainnetQuote(null)
    try {
      const result = await api.fundingMainnetQuote({
        source_asset: mainnetActiveAsset.asset_id,
        destination_asset: mainnetData.destination_asset,
        source_chain: mainnetActiveAsset.blockchain,
        deposit_type: 'ORIGIN_CHAIN',
        amount: mainnetRawAmount,
        recipient: mainnetTargetRecipient,
        refund_to: mainnetRefundTo.trim(),
        slippage_bps: 100,
        deadline_minutes: 15,
        dry: true,
      })
      setMainnetQuote(result.data)
    } catch (reason) {
      setMainnetError(errorText(reason))
    } finally {
      setMainnetBusy(false)
    }
  }

  async function requestDryQuote() {
    if (!activeAsset || !rawAmount || !refundTo.trim()) return
    setBusy(true)
    setError(null)
    setDryResult(null)
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
      setDryResult(result.data)
      setLiveConfirmed(false)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setBusy(false)
    }
  }

  async function requestLiveQuote() {
    if (!activeAsset || !rawAmount || !refundTo.trim() || activeChain !== 'base') return
    setBusy(true)
    setError(null)
    setLiveResult(null)
    setStatus(null)
    setTxHash('')
    setPollCount(0)
    try {
      const result = await api.fundingLiveQuote({
        source_asset: activeAsset.asset_id,
        source_chain: activeAsset.blockchain,
        amount: rawAmount,
        recipient: accountId,
        refund_to: refundTo.trim(),
        deposit_type: 'ORIGIN_CHAIN',
        slippage_bps: 100,
        deadline_minutes: 15,
        dry: false,
        confirm_live_quote: true,
        confirm_testnet: true,
      })
      setLiveResult(result.data)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setBusy(false)
    }
  }

  async function submitDepositHash() {
    if (!liveResult || !txValid) return
    setStatusBusy(true)
    setError(null)
    try {
      const response = await api.fundingDeposit({
        quote_id: liveResult.quote.quote_id,
        tx_hash: txHash.trim(),
        submit: true,
        user_confirmed: true,
      })
      setStatus(response.data)
      setPollCount(0)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setStatusBusy(false)
    }
  }

  async function refreshStatus() {
    if (!liveResult) return
    setStatusBusy(true)
    setError(null)
    try {
      const response = await api.fundingStatus(liveResult.quote.quote_id, true)
      setStatus(response.data)
      setPollCount((count) => Math.min(12, count + 1))
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setStatusBusy(false)
    }
  }

  function clearLiveFlow() {
    setLiveResult(null)
    setStatus(null)
    setTxHash('')
    setLiveConfirmed(false)
    setPollCount(0)
    setVerifiedNotified(false)
    if (typeof window !== 'undefined') window.localStorage.removeItem(FUNDING_STORAGE_KEY)
  }

  const providerQuote = dryResult?.provider_quote.quote
  const liveProviderQuote = liveResult?.provider_quote.quote
  const mainnetProviderQuote = mainnetQuote?.provider_quote.quote
  const settlement = status?.settlement_evidence

  return (
    <div className="card fund" aria-label="Fund Notch Wallet">
      <div className="fund-intro">
        <div>
          <p className="eyebrow">Testnet bridge · manual approval</p>
          <h3>Fund Notch Wallet</h3>
          <p className="dim">Prepare one verified Base Sepolia route into your connected NEAR Testnet wallet. Notch never signs or broadcasts the source-chain transaction.</p>
        </div>
        <span className="badge">TESTNET ONLY</span>
      </div>

      <div className="fund-boundary" role="note">
        <strong>{data?.network ?? 'Tidepool Testnet'}</strong>
        <span>{data?.provider ?? 'Tidepool'}. Tidepool is a community-operated testnet sandbox, not the production NEAR Intents service. Test tokens have no value.</span>
      </div>

      <section className="fund-mainnet" aria-labelledby="fund-mainnet-heading">
        <div className="fund-quote-head">
          <div>
            <p className="eyebrow">Official provider · future production access</p>
            <h4 id="fund-mainnet-heading">NEAR Intents 1Click Mainnet</h4>
          </div>
          <span className="badge badge-replay">READ-ONLY / FUTURE</span>
        </div>
        {mainnetTokens.status === 'loading' && <p className="dim">Checking official Mainnet token discovery…</p>}
        {mainnetTokens.status === 'error' && <p className="fund-warning">Official Mainnet discovery is unavailable. No Mainnet route is enabled.</p>}
        {mainnetData && (
          <>
            <p className="dim">{mainnetData.provider} · {mainnetData.environment}. This surface never funds the current NEAR Testnet market or its Testnet collateral.</p>
            <dl className="kv kv-tight fund-quote-meta">
              <div><dt>Live catalog</dt><dd>{mainnetData.tokens.length} assets · {mainnetData.source_chains.length} source chains</dd></div>
              <div><dt>Authentication</dt><dd>{mainnetData.auth_configured ? 'Partner JWT configured server-side' : 'Unauthenticated public API'}</dd></div>
              <div><dt>Quote mode</dt><dd>{mainnetData.quote_mode === 'dry_only' ? 'Genuine dry quotes only' : 'Unavailable'}</dd></div>
              <div><dt>Execution</dt><dd>Disabled · {mainnetData.execution_reasons[0]}</dd></div>
            </dl>
            <p className="fund-warning" role="note">{mainnetData.fee_notice}</p>
            {mainnetData.unavailable_reasons.length > 0 && <ul className="fund-instructions">{mainnetData.unavailable_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
            {mainnetData.quote_enabled && mainnetData.destination_asset && (
              <div className="fund-mainnet-form">
                <div className="fund-row fund-row-four">
                  <label className="field" style={{ marginTop: 0 }}>
                    <span>Mainnet source asset</span>
                    <select className="field-in sel" value={mainnetActiveAsset?.asset_id ?? ''} onChange={(event) => { setMainnetSourceAsset(event.target.value); setMainnetQuote(null) }}>
                      {mainnetSourceTokens.map((token) => <option key={token.asset_id} value={token.asset_id}>{token.symbol} · {token.blockchain} · {token.decimals} decimals</option>)}
                    </select>
                  </label>
                  <label className="field" style={{ marginTop: 0 }}>
                    <span>Mainnet recipient account</span>
                    <input id="fund-mainnet-recipient" className="field-in" value={mainnetRecipient || mainnetData.recipient || ''} placeholder="yourname.near" onChange={(event) => { setMainnetRecipient(event.target.value); setMainnetQuote(null) }} />
                  </label>
                  <label className="field" style={{ marginTop: 0 }}>
                    <span>Mainnet amount</span>
                    <div className="field-in"><input id="fund-mainnet-amount" inputMode="decimal" placeholder="0.0" value={mainnetAmount} onChange={(event) => { setMainnetAmount(event.target.value.replace(/[^\d.]/g, '')); setMainnetQuote(null) }} /><span className="dim">{mainnetActiveAsset?.symbol}</span></div>
                  </label>
                  <label className="field" style={{ marginTop: 0 }}>
                    <span>Source-chain refund address</span>
                    <input id="fund-mainnet-refund" className="field-in fund-refund" value={mainnetRefundTo} placeholder={inputHint(mainnetActiveAsset?.blockchain ?? '')} onChange={(event) => { setMainnetRefundTo(event.target.value); setMainnetQuote(null) }} />
                  </label>
                </div>
                <p className="fine">Mainnet recipient: <span className="mono">{mainnetTargetRecipient || 'enter a .near account'}</span> · destination: <span className="mono hash">{mainnetData.destination_asset}</span></p>
                <button className="btn btn-quiet" onClick={requestMainnetDryQuote} disabled={!mainnetCanQuote}>{mainnetBusy ? 'Requesting Mainnet dry quote…' : 'Inspect official Mainnet dry quote'}</button>
              </div>
            )}
            {mainnetError && <p className="fine err" role="alert">{mainnetError}</p>}
            {mainnetQuote && mainnetProviderQuote && (
              <section className="fund-quote fund-mainnet-quote" aria-labelledby="fund-mainnet-quote-heading" aria-live="polite">
                <div className="fund-quote-head"><div><p className="eyebrow">Genuine provider response · official dry=true</p><h5 id="fund-mainnet-quote-heading">Mainnet route review</h5></div><span className="badge badge-replay">NO TRANSFER</span></div>
                <div className="fund-quote-grid">
                  <div><span>You would send</span><strong className="mono">{formatUnits(mainnetQuote.quote.amount_in, mainnetQuote.quote.source_decimals, 8)} {mainnetQuote.quote.source_symbol}</strong><small>{mainnetProviderQuote.amount_in} source units</small></div>
                  <div><span>Estimated output</span><strong className="mono">{formatUnits(mainnetQuote.quote.amount_out, mainnetQuote.quote.destination_decimals ?? 0, 8)} {mainnetQuote.quote.destination_symbol}</strong><small>{mainnetProviderQuote.amount_out} destination units</small></div>
                  <div><span>Minimum output</span><strong className="mono">{formatUnits(mainnetQuote.quote.min_amount_out, mainnetQuote.quote.destination_decimals ?? 0, 8)} {mainnetQuote.quote.destination_symbol}</strong><small>After {((mainnetQuote.quote.slippage_bps ?? 100) / 100).toFixed(2)}% slippage</small></div>
                  <div><span>Provider fees</span><strong className="mono">refund {mainnetProviderQuote.refund_fee ?? '—'} · withdraw {mainnetProviderQuote.withdraw_fee ?? '—'}</strong><small>Base units returned by 1Click</small></div>
                </div>
                <dl className="kv kv-tight fund-quote-meta">
                  <div><dt>Origin asset</dt><dd className="mono hash">{mainnetQuote.quote.source_asset}</dd></div>
                  <div><dt>Destination asset</dt><dd className="mono hash">{mainnetQuote.quote.destination_asset}</dd></div>
                  <div><dt>Signature</dt><dd>{mainnetQuote.validation.signature_verified ? 'Verified against official 1Click manager key' : 'Not verified'}</dd></div>
                  <div><dt>Freshness</dt><dd>{mainnetQuote.quote.expires_at ? `${relativeTo(mainnetQuote.quote.expires_at)} · expires ${formatUtc(mainnetQuote.quote.expires_at)}` : 'No expiry returned'}</dd></div>
                </dl>
                <p className="fund-warning">Read-only Mainnet preview. No deposit address, wallet authorization, signing, broadcast, or Testnet collateral funding is available.</p>
              </section>
            )}
          </>
        )}
      </section>

      {data && data.source_chains.length > 0 && sourceTokens.length > 0 ? (
        <>
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
            <input id="fund-amount" inputMode="decimal" placeholder="0.0" value={amount} aria-invalid={invalidAmount || undefined} aria-describedby={invalidAmount ? 'fund-amount-error' : undefined} onChange={(event) => { setAmount(event.target.value.replace(/[^\d.]/g, '')); setDryResult(null); setLiveResult(null); setStatus(null) }} />
            <span className="dim">{activeAsset?.symbol}</span>
          </div>
          {invalidAmount && <small id="fund-amount-error" className="err">Use up to {activeAsset?.decimals} decimal places.</small>}
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
          <input id="fund-refund" className="field-in fund-refund" value={refundTo} placeholder={inputHint(activeChain)} aria-describedby="fund-refund-help" onChange={(event) => { setRefundTo(event.target.value); setDryResult(null); setLiveResult(null); setStatus(null) }} />
          <small id="fund-refund-help">Required and validated for the selected source chain. Use an address you control.</small>
        </label>
      </div>

      <div className="fund-review-line">
        <span>Route: <strong>{activeAsset?.symbol} · {chainLabel(activeChain)}</strong> → <strong>test-USDC · NEAR Testnet</strong></span>
        <span>Slippage cap: <strong>1%</strong> · Dry quote window: <strong>30 min</strong></span>
      </div>

      <div className="row-gap fund-actions">
        <button className="btn btn-primary" onClick={requestDryQuote} disabled={!canQuote}>{busy ? 'Requesting quote…' : 'Inspect genuine dry quote'}</button>
        <a className="btn btn-quiet" href="https://www.usetidepool.tech/docs/quickstart" target="_blank" rel="noreferrer">Provider docs <span aria-hidden="true">↗</span></a>
      </div>

      {error && <p className="fine err" role="alert" aria-live="assertive">{error}</p>}

      {dryResult && quote && providerQuote && (
        <section className="fund-quote" aria-labelledby="fund-dry-heading" aria-live="polite">
          <div className="fund-quote-head">
            <div>
              <p className="eyebrow">Genuine provider response · dry=true</p>
              <h4 id="fund-dry-heading">Route review</h4>
            </div>
            <span className="badge badge-replay">NO TRANSFER</span>
          </div>
          <div className="fund-quote-grid">
            <div><span>You would send</span><strong className="mono">{formatUnits(quote.amount_in, quote.source_decimals, 8)} {quote.source_symbol}</strong><small>{providerQuote.amount_in_formatted} source units</small></div>
            <div><span>Estimated output</span><strong className="mono">{formatUnits(quote.amount_out, quote.destination_decimals, 8)} {quote.destination_symbol}</strong><small>{providerQuote.amount_out_formatted} destination units</small></div>
            <div><span>Minimum output</span><strong className="mono">{formatUnits(quote.min_amount_out, quote.destination_decimals, 8)} {quote.destination_symbol}</strong><small>After {((quote.slippage_bps ?? 100) / 100).toFixed(2)}% slippage</small></div>
            <div><span>Provider signature</span><strong>{dryResult.validation.signature_verified ? 'Verified' : 'Shape checked'}</strong><small>Maker signature retained with the quote</small></div>
          </div>
          <dl className="kv kv-tight fund-quote-meta">
            <div><dt>Origin asset</dt><dd className="mono hash">{quote.source_asset}</dd></div>
            <div><dt>Destination asset</dt><dd className="mono hash">{quote.destination_asset}</dd></div>
            <div><dt>Recipient</dt><dd className="mono hash">{quote.recipient}</dd></div>
            <div><dt>Refund destination</dt><dd className="mono hash">{quote.refund_to}</dd></div>
            <div><dt>Quote freshness</dt><dd>{quote.expires_at ? `${relativeTo(quote.expires_at)} · expires ${formatUtc(quote.expires_at)}` : 'No expiry returned'}</dd></div>
          </dl>
          <p className="fund-warning" role="note">This is a price preview only. It did not create a deposit address, authorize a wallet, or move funds.</p>
          {activeChain === 'base' ? (
            <div className="fund-live-handoff">
              <label className="fund-confirm">
                <input type="checkbox" checked={liveConfirmed} onChange={(event) => setLiveConfirmed(event.target.checked)} />
                <span>I reviewed the Base Sepolia → NEAR Testnet route and authorize Notch to request one live quote with a single-use deposit address. I understand no transfer will be sent automatically.</span>
              </label>
              <button className="btn btn-primary" onClick={requestLiveQuote} disabled={!canLiveQuote}>{busy ? 'Preparing live quote…' : 'Request live deposit instructions'}</button>
            </div>
          ) : (
            <p className="fund-warning" role="note">Live deposits are not enabled for this source chain in Phase 7B V1. Select Base Sepolia for the first supported route.</p>
          )}
        </section>
      )}

      {liveResult && liveQuote && liveProviderQuote && liveInstructions && (
        <section className="fund-quote fund-live" aria-labelledby="fund-live-heading" aria-live="polite">
          <div className="fund-quote-head">
            <div>
              <p className="eyebrow">Live quote · dry=false</p>
              <h4 id="fund-live-heading">Deposit instructions ready</h4>
            </div>
            <span className="badge">USER APPROVAL REQUIRED</span>
          </div>
          <div className="fund-quote-grid">
            <div><span>Send exactly</span><strong className="mono">{formatUnits(liveQuote.amount_in, liveQuote.source_decimals, 8)} {liveQuote.source_symbol}</strong><small>{liveQuote.amount_in} base units</small></div>
            <div><span>Minimum output</span><strong className="mono">{formatUnits(liveQuote.min_amount_out, liveQuote.destination_decimals, 8)} {liveQuote.destination_symbol}</strong><small>{liveQuote.min_amount_out} base units</small></div>
            <div><span>Provider status</span><strong>{statusLabel(currentStatus)}</strong><small>{liveQuote.signature_verified ? 'Quote signature verified' : 'Signature shape checked'}</small></div>
            <div><span>Deadline</span><strong>{liveQuote.expires_at ? relativeTo(liveQuote.expires_at) : '—'}</strong><small>{liveQuote.expires_at ? formatUtc(liveQuote.expires_at) : 'No deadline returned'}</small></div>
          </div>
          <dl className="kv kv-tight fund-quote-meta">
            <div><dt>Base Sepolia chain ID</dt><dd>84532</dd></div>
            <div><dt>Token contract</dt><dd className="mono hash">{activeAsset?.contract_address ?? liveQuote.source_asset}</dd></div>
            <div><dt>Provider deposit address</dt><dd className="mono hash">{liveInstructions.provider_deposit_address} <a href={`https://sepolia.basescan.org/address/${liveInstructions.provider_deposit_address}`} target="_blank" rel="noreferrer">explorer ↗</a></dd></div>
            <div><dt>Deposit memo</dt><dd className="mono hash">{liveInstructions.deposit_memo || 'None returned; do not invent one.'}</dd></div>
            <div><dt>NEAR recipient</dt><dd className="mono hash">{liveQuote.recipient}</dd></div>
            <div><dt>Refund destination</dt><dd className="mono hash">{liveQuote.refund_to}</dd></div>
          </dl>
          <ul className="fund-instructions">
            {liveInstructions.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
          <p className="fund-warning" role="note">Notch has not signed or broadcast a Base transaction. Use a wallet you control on Base Sepolia, verify the contract and amount, and approve exactly one ERC-20 transfer to the provider address above. Never send Mainnet assets.</p>
          {!status?.deposit_submitted && !isTerminal && (
            <div className="fund-submit">
              <label className="field" style={{ marginTop: 0 }}>
                <span>Source transaction hash</span>
                <input id="fund-tx-hash" className="field-in mono" inputMode="text" placeholder="0x… 64 hex characters" value={txHash} aria-describedby="fund-tx-help" onChange={(event) => setTxHash(event.target.value.trim())} />
                <small id="fund-tx-help">After you approve the exact transfer in your external Base Sepolia wallet, paste the transaction hash here. Notch only submits this reference to Tidepool.</small>
              </label>
              <button className="btn btn-primary" onClick={submitDepositHash} disabled={!canSubmitDeposit}>{statusBusy ? 'Submitting reference…' : 'Submit transaction hash to Tidepool'}</button>
            </div>
          )}
          {status?.deposit_submitted && !isTerminal && <p className="fund-status" role="status">Tidepool has the transaction reference. Status polling is bounded to 12 checks; you can refresh manually.</p>}
          {status && (
            <div className="fund-status-card" data-state={status.state}>
              <div className="fund-status-head"><strong>{statusLabel(status.provider_status)}</strong><button className="btn btn-quiet" onClick={refreshStatus} disabled={statusBusy}>{statusBusy ? 'Checking…' : 'Check status now'}</button></div>
              <dl className="kv kv-tight fund-quote-meta">
                <div><dt>Provider state</dt><dd className="mono">{status.provider_status || 'Not submitted'}</dd></div>
                <div><dt>Destination verification</dt><dd className="mono">{destinationState || 'Not started'}</dd></div>
                <div><dt>Balance delta</dt><dd className="mono">{status.destination_verification?.balance_delta ?? '—'} base units</dd></div>
                <div><dt>Deposit transaction</dt><dd className="mono hash">{status.deposit_tx_hash ? <a href={explorerTx(status.deposit_tx_hash)} target="_blank" rel="noreferrer">{status.deposit_tx_hash} ↗</a> : '—'}</dd></div>
                <div><dt>Last error</dt><dd>{status.last_error || '—'}</dd></div>
              </dl>
              {status.provider_status === 'SUCCESS' && destinationState === 'DESTINATION_VERIFICATION_PENDING' && <p className="fund-warning">Provider SUCCESS is not enough yet. Notch is waiting for an independent NEP-141 balance increase on {status.recipient}; it will not display funded until that check passes.</p>}
              {destinationState === 'DESTINATION_VERIFIED' && <p className="fund-success" role="status">Destination verified: {status.destination_symbol} arrived at the requested NEAR Testnet wallet.</p>}
              {status.provider_status === 'REFUNDED' && <p className="fund-warning" role="alert">Tidepool reports REFUNDED. Do not treat this as funded; check the refund destination and provider evidence.</p>}
              {status.provider_status === 'FAILED' && <p className="fund-warning" role="alert">Tidepool reports FAILED. No funded balance is claimed. Review the provider reason before retrying with a fresh quote.</p>}
              {settlement && (settlement.near_tx_hashes.length > 0 || settlement.destination_chain_tx_hashes.length > 0) && <div className="fund-evidence"><strong>Settlement evidence</strong>{settlement.near_tx_hashes.map((hash) => <a key={hash} href={`https://testnet.nearblocks.io/txns/${hash}`} target="_blank" rel="noreferrer">NEAR transaction {hash} ↗</a>)}{settlement.destination_chain_tx_hashes.map((tx) => <a key={tx.hash} href={tx.explorer_url || `https://testnet.nearblocks.io/txns/${tx.hash}`} target="_blank" rel="noreferrer">Destination transaction {tx.hash} ↗</a>)}</div>}
            </div>
          )}
          <div className="row-gap fund-actions"><Link className="btn btn-quiet" to="/app/markets?f=open">Continue to open prediction markets <span aria-hidden="true">→</span></Link><button className="btn btn-quiet" onClick={clearLiveFlow}>Start a new quote</button></div>
        </section>
      )}
        </>
      ) : (
        <p className="dim">{tokens.status === 'loading' ? 'Checking Tidepool Testnet funding discovery…' : 'Tidepool Testnet discovery is unavailable right now. The official Mainnet panel above remains read-only.'}</p>
      )}
    </div>
  )
}
