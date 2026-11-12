import { useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useApi } from '../api/useApi'
import type { FundingInstructions, FundingQuote } from '../api/types'
import { formatUnits, parseUnits, relativeTo } from '../api/format'
import { explorerTx, useWallet } from '../wallet/WalletProvider'

const TERMINAL = new Set(['SUCCESS', 'REFUNDED', 'FAILED', 'EXPIRED'])

/**
 * Swap a Tidepool testnet token into test-USDC via the S4 funding route (ORIGIN_CHAIN).
 * The user signs the provider's exact deposit steps; success is shown only when S4 reports
 * SUCCESS with a verified USDC balance increase.
 */
export function Funding({ accountId, onFunded }: { accountId: string; onFunded: () => void }) {
  const { signAndSend } = useWallet()
  const [tokens] = useApi(() => api.fundingTokens().then((r) => r.data), [])
  const routes = tokens.status === 'ok' ? tokens.data.routes.filter((r) => r.source.blockchain === 'near') : []
  const [src, setSrc] = useState<string>('')
  const route = routes.find((r) => r.source.asset_id === src) ?? routes[0]
  const [amount, setAmount] = useState('')
  const raw = route ? parseUnits(amount, route.source.decimals) : null

  const [preview, setPreview] = useState<FundingQuote | null>(null)
  const [live, setLive] = useState<{ quote: FundingQuote; instructions?: FundingInstructions } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [hash, setHash] = useState<string | null>(null)
  const poll = useRef<number | null>(null)

  useEffect(() => () => { if (poll.current) clearInterval(poll.current) }, [])
  useEffect(() => { setPreview(null); setLive(null); setErr(null) }, [src, amount])

  const body = useMemo(() => raw && route ? {
    source_asset: route.source.asset_id, amount: raw, recipient: accountId, refund_to: accountId,
    deposit_type: 'ORIGIN_CHAIN' as const, slippage_bps: 100, deadline_minutes: 30,
  } : null, [raw, route, accountId])

  async function getPreview() {
    if (!body) return
    setBusy('preview'); setErr(null)
    try { setPreview((await api.fundingQuote({ ...body, dry: true })).data.quote) }
    catch (e) { setErr(e instanceof ApiError ? e.message : String(e)) }
    finally { setBusy(null) }
  }

  async function getLive() {
    if (!body) return
    setBusy('live'); setErr(null)
    try {
      const r = (await api.fundingQuote({ ...body, dry: false })).data
      if (!r.instructions?.supported || !r.instructions.steps.length) throw new Error(r.instructions?.blocker ?? 'The provider returned no deposit instructions.')
      setLive(r)
    } catch (e) { setErr(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)) }
    finally { setBusy(null) }
  }

  function startPolling(quoteId: string) {
    if (poll.current) clearInterval(poll.current)
    poll.current = window.setInterval(async () => {
      try {
        const q = (await api.fundingStatus(quoteId, true)).data.quote
        setLive((l) => (l ? { ...l, quote: q } : l))
        if (TERMINAL.has(q.state)) { clearInterval(poll.current!); poll.current = null; if (q.state === 'SUCCESS') onFunded() }
      } catch { /* keep polling; 429/503 are transient */ }
    }, 6000)
  }

  async function deposit() {
    if (!live?.instructions) return
    const steps = live.instructions.steps
    const receiver = steps[0].contract
    if (steps.some((s) => s.contract !== receiver)) { setErr('Deposit steps target different contracts; cannot batch safely.'); return }
    setBusy('deposit'); setErr(null)
    try {
      const res = await signAndSend({
        receiverId: receiver,
        calls: steps.map((s) => ({ methodName: s.method, args: s.args, gasTgas: s.gas_tgas, depositYocto: s.attached_deposit_yocto })),
      })
      setHash(res.hash)
      startPolling(live.quote.quote_id)
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(null) }
  }

  if (tokens.status === 'loading') return <div className="skeleton" style={{ height: 180 }} />
  if (tokens.status === 'error') return <p className="dim">Funding routes are unavailable right now.</p>
  if (!route) return <p className="dim">No NEAR Testnet funding route is available.</p>

  const q = live?.quote
  const outDec = q?.destination_decimals ?? 6
  return (
    <div className="card fund">
      <p className="dim" style={{ marginBottom: 14 }}>Swap a Tidepool testnet token you hold into test-USDC. Testnet only — these tokens have no value.</p>
      {!live && (
        <>
          <div className="fund-row">
            <label className="field" style={{ marginTop: 0 }}>
              <span>From</span>
              <select className="field-in sel" value={route.source.asset_id} onChange={(e) => setSrc(e.target.value)}>
                {routes.map((r) => <option key={r.source.asset_id} value={r.source.asset_id}>{r.source.symbol}</option>)}
              </select>
            </label>
            <label className="field" style={{ marginTop: 0 }}>
              <span>Amount</span>
              <div className="field-in"><input inputMode="decimal" placeholder="0.0" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} /><span className="dim">{route.source.symbol}</span></div>
            </label>
          </div>
          {preview && (
            <p className="fine">Quote: about <span className="mono txt">{formatUnits(preview.amount_out, preview.destination_decimals, 4)}</span> test-USDC, minimum <span className="mono txt">{formatUnits(preview.min_amount_out, preview.destination_decimals, 4)}</span> after 1% slippage. Price preview only — no deposit address yet.</p>
          )}
          <div className="row-gap">
            <button className="btn btn-quiet" onClick={getPreview} disabled={!body || !!busy}>{busy === 'preview' ? 'Quoting…' : 'Preview'}</button>
            <button className="btn btn-primary" onClick={getLive} disabled={!preview || !!busy}>{busy === 'live' ? 'Requesting…' : 'Get deposit instructions'}</button>
          </div>
        </>
      )}

      {live && q && (
        <>
          <dl className="kv kv-tight">
            <div><dt>You send</dt><dd className="mono">{formatUnits(q.amount_in, q.source_decimals, 6)} {q.source_symbol}</dd></div>
            <div><dt>Min. received</dt><dd className="mono">{formatUnits(q.min_amount_out, outDec, 6)} test-USDC</dd></div>
            <div><dt>Deposit account</dt><dd className="mono hash">{q.deposit_address}</dd></div>
            <div><dt>Expires</dt><dd>{relativeTo(q.expires_at)}</dd></div>
            <div><dt>Status</dt><dd><strong className="txt">{q.state}</strong>{q.provider_status && <span className="dim"> · provider {q.provider_status}</span>}</dd></div>
          </dl>
          <ol className="steps">
            {live.instructions!.steps.map((s) => <li key={s.step}><span className="mono">{s.contract}.{s.method}</span> <span className="dim">· {s.note ?? s.action}</span></li>)}
          </ol>
          {q.state === 'SUCCESS' && q.balance_verified
            ? <p className="ok" role="status">Received {q.balance_delta ? formatUnits(q.balance_delta, outDec, 6) : ''} test-USDC — balance increase verified.</p>
            : TERMINAL.has(q.state)
              ? <p className="err" role="status">Funding {q.state.toLowerCase()}.{q.last_error ? ` ${q.last_error}` : ''}</p>
              : hash || q.deposit_submitted
                ? <p className="dim" role="status" aria-live="polite">Deposit sent. Waiting for the provider and a verified balance increase…</p>
                : <button className="btn btn-primary w100" onClick={deposit} disabled={!!busy}>{busy === 'deposit' ? 'Waiting for wallet…' : 'Sign deposit in wallet'}</button>}
          {hash && <p className="fine"><a className="link" href={explorerTx(hash)} target="_blank" rel="noreferrer">View deposit transaction</a></p>}
          <button className="btn btn-ghost w100" onClick={() => { if (poll.current) clearInterval(poll.current); setLive(null); setHash(null) }}>Start over</button>
        </>
      )}
      {err && <p className="fine err" role="alert">{err}</p>}
    </div>
  )
}
