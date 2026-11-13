import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market, Position } from '../api/types'
import { cleanQuestion, formatUnits, sumUnits, USDC_DECIMALS } from '../api/format'
import { PREDICTION_STATUS_HELP, PREDICTION_STATUS_LABEL, predictionBadgeClass, predictionStatus, selectedChoices, shortEvidence } from '../api/predictions'
import { ErrorState, SkeletonList, Unavailable } from '../components/States'
import { marketTitle } from '../components/market'
import { explorerAccount, explorerTx, useWallet } from '../wallet/WalletProvider'
import { Funding } from './Funding'
import { ShareCallButton } from '../share/ShareButtons'
import './Portfolio.css'

export const MARKET_CONTRACT = (import.meta.env.VITE_MARKET_CONTRACT as string | undefined) ?? 'market.notch-dev.testnet'
const FINAL = new Set(['resolved', 'voided'])

interface Row extends Position { replay: boolean; market?: Market }

/** Every figure is derived from contract reads via S6. Nothing is estimated. */
function summarize(rows: Row[]) {
  const active = rows.filter((p) => !FINAL.has(p.market_status))
  const settled = rows.filter((p) => FINAL.has(p.market_status) && (p.claim_state === 'claimed' || p.claim_state === 'not_eligible'))
  const settledLive = settled.filter((p) => !p.replay)
  return {
    staked: sumUnits(active.map((p) => p.total_stake)),
    active: active.length,
    claimable: sumUnits(rows.map((p) => p.claimable)),
    received: sumUnits(rows.map((p) => p.claimed_total)),
    // Realized P/L = paid out − staked, only for fully settled positions on future-outcome markets.
    realized: settledLive.length ? (BigInt(sumUnits(settledLive.map((p) => p.claimed_total))) - BigInt(sumUnits(settledLive.map((p) => p.total_stake)))).toString() : null,
    hasPending: rows.some((p) => p.claim_state === 'pending' || p.claim_state === 'claimable'),
  }
}

export function Portfolio() {
  const { accountId, connect, ready } = useWallet()
  if (!accountId) {
    return (
      <>
        <header className="page-head"><div><h1>Portfolio</h1><p>Balances and positions read directly from NEAR Testnet.</p></div></header>
        <Unavailable title="Connect a wallet to see your portfolio">
          Notch reads balances and positions from the blockchain for the wallet you connect. Nothing here is simulated.
        </Unavailable>
        <div style={{ textAlign: 'center' }}><button className="btn btn-primary" onClick={connect} disabled={!ready}>Connect Wallet</button></div>
      </>
    )
  }
  return <Connected accountId={accountId} />
}

function Connected({ accountId }: { accountId: string }) {
  const { disconnect } = useWallet()
  const [bal, reloadBal] = useApi(() => api.balances(accountId).then((r) => r.data), [accountId])
  const [pos, reloadPos] = useApi(() => Promise.all([api.positions(accountId), api.markets()]).then(([p, m]) => {
    const byId = new Map<string, Market>(m.data.map((x) => [x.market_id, x]))
    return p.data.map((x): Row => ({ ...x, replay: byId.get(x.market_id)?.is_historical_replay ?? false, market: byId.get(x.market_id) }))
  }), [accountId])
  const reload = () => { reloadBal(); reloadPos() }
  const s = useMemo(() => (pos.status === 'ok' ? summarize(pos.data) : null), [pos])

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Portfolio</h1>
          <p><a className="link" href={explorerAccount(accountId)} target="_blank" rel="noreferrer">{accountId}</a> · NEAR Testnet</p>
        </div>
        <button className="btn btn-ghost" onClick={() => disconnect()}>Disconnect</button>
      </header>

      <section className="stats" aria-label="Summary">
        <Stat label="Available test-USDC" value={bal.status === 'ok' ? formatUnits(bal.data.collateral.balance, USDC_DECIMALS) : null} loading={bal.status === 'loading'} />
        <Stat label="Currently staked" value={s ? formatUnits(s.staked, USDC_DECIMALS) : null} loading={!s} />
        <Stat label="Active positions" value={s ? String(s.active) : null} loading={!s} unit="" />
        <Stat label="Claimable payouts" value={s ? formatUnits(s.claimable, USDC_DECIMALS) : null} loading={!s} accent={!!s && s.claimable !== '0'} />
        <Stat label="Total payouts received" value={s ? formatUnits(s.received, USDC_DECIMALS) : null} loading={!s} />
        <Stat label="Realized P/L" loading={!s}
          value={s?.realized != null ? `${BigInt(s.realized) > 0n ? '+' : ''}${formatUnits(s.realized, USDC_DECIMALS)}` : null}
          empty="Not available yet"
          hint="Paid out minus staked, for settled future-outcome markets only. Resolved demonstrations are excluded." />
      </section>
      {bal.status === 'ok' && (
        <p className="fine" style={{ marginTop: -8, marginBottom: 28 }}>
          NEAR for fees: <span className="mono txt">{formatUnits(bal.data.near.yocto_near, 24, 4)}</span>
          {bal.data.tokens.filter((t) => t.symbol !== 'USDC' && t.balance !== '0').map((t) => (
            <span key={t.asset_id}> · {t.symbol} <span className="mono txt">{formatUnits(t.balance, t.decimals)}</span></span>
          ))}
        </p>
      )}

      <section className="msec" aria-labelledby="pos-h">
        <h2 id="pos-h" className="msec-h">Your positions</h2>
        {pos.status === 'loading' && <SkeletonList n={2} h={88} />}
        {pos.status === 'error' && <ErrorState error={pos.error} onRetry={reloadPos} />}
        {pos.status === 'ok' && (pos.data.length === 0
          ? <div className="state"><h2>No positions yet</h2><p>Take a position on an open market to see it here.</p><Link to="/app/markets?f=open" className="btn btn-quiet" style={{ marginTop: 16 }}>Open markets</Link></div>
          : <div className="plist">{pos.data.map((p) => <PositionRow key={p.market_id} p={p} accountId={accountId} onChange={reload} />)}</div>)}
      </section>

      <section className="msec" id="fund" aria-labelledby="fund-h">
        <h2 id="fund-h" className="msec-h">Get test-USDC</h2>
        <Funding accountId={accountId} onFunded={reloadBal} />
      </section>
    </>
  )
}

function Stat({ label, value, loading, unit = 'USDC', hint, empty = '—', accent }: { label: string; value: string | null; loading: boolean; unit?: string; hint?: string; empty?: string; accent?: boolean }) {
  return (
    <div className={`stat${accent ? ' is-accent' : ''}`} title={hint}>
      <p className="stat-l">{label}</p>
      {loading ? <div className="skeleton" style={{ height: 30, width: '60%', marginTop: 6 }} />
        : value == null ? <p className="stat-empty">{empty}</p>
        : <p className="stat-v mono">{value}{unit && <span className="stat-u"> {unit}</span>}</p>}
      {hint && !loading && <p className="stat-h">{hint}</p>}
    </div>
  )
}

const CLAIM_LABEL: Record<string, string> = { open: 'Open', pending: 'Payout pending', claimable: 'Claimable', claimed: 'Settled', not_eligible: 'Settled · no payout' }

function PositionRow({ p, accountId, onChange }: { p: Row; accountId: string; onChange: () => void }) {
  const { signAndSend } = useWallet()
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ text: string; hash?: string | null; err?: boolean } | null>(null)

  async function claim() {
    setBusy('claim'); setMsg(null)
    const before = p.claimed_total
    try {
      const res = await signAndSend({ receiverId: MARKET_CONTRACT, calls: [{ methodName: 'claim', args: { market_id: p.market_id }, gasTgas: 100, depositYocto: '0' }] })
      if (res.redirected) return
      for (let i = 0; i < 10; i++) {
        const r = await api.positions(accountId)
        const now = r.data.find((x) => x.market_id === p.market_id)
        if (now && BigInt(now.claimed_total) > BigInt(before)) { setMsg({ text: `Claimed ${formatUnits((BigInt(now.claimed_total) - BigInt(before)).toString(), USDC_DECIMALS, 6)} test-USDC.`, hash: res.hash }); onChange(); return }
        await new Promise((r2) => setTimeout(r2, 3000))
      }
      setMsg({ text: 'Claim not confirmed by the contract yet. Check the explorer.', hash: res.hash, err: true })
    } catch (e) {
      setMsg({ text: e instanceof Error ? e.message : String(e), err: true })
    } finally { setBusy(null) }
  }

  const headline = p.market ? marketTitle(p.market) : cleanQuestion(p.question)
  const settlementRule = cleanQuestion(p.question)
  const called = selectedChoices(p)

  return (
    <div className="prow">
      <div className="prow-main">
        <Link to={`/app/markets/${encodeURIComponent(p.market_id)}`} className="prow-title" title={settlementRule}>{headline}</Link>
        <p className="prow-meta">
          {p.replay && <span className="badge badge-replay">Resolved demonstration · not counted</span>}
          <span className="dim">Prediction</span>
          <span className={`badge ${predictionBadgeClass(predictionStatus(p))}`} title={PREDICTION_STATUS_HELP[predictionStatus(p)]}>{PREDICTION_STATUS_LABEL[predictionStatus(p)]}</span>
          <span className="dim">Payout</span>
          <span className="badge">{CLAIM_LABEL[p.claim_state] ?? p.claim_state}</span>
          {called.length > 0 && <span className="dim">Called {called.join(' / ')}</span>}
          {p.winning_choice && <span className="dim">Final outcome {p.winning_choice}</span>}
          {shortEvidence(p.evidence_hash) && <span className="mono dim">Evidence {shortEvidence(p.evidence_hash)}</span>}
        </p>
        <details className="prow-rule">
          <summary>Full settlement rule</summary>
          <p>{settlementRule}</p>
        </details>
      </div>
      <dl className="prow-nums">
        <div><dt>Staked</dt><dd className="mono">{formatUnits(p.total_stake, USDC_DECIMALS)}</dd></div>
        <div><dt>Received</dt><dd className="mono">{formatUnits(p.claimed_total, USDC_DECIMALS)}</dd></div>
        {p.claimable !== '0' && <div><dt>Claimable</dt><dd className="mono ok">{formatUnits(p.claimable, USDC_DECIMALS)}</dd></div>}
      </dl>
      {p.market && !p.replay && (() => {
        const i = p.stakes.findIndex((s) => s !== '0')
        return called.length === 1 && i >= 0 ? <ShareCallButton className="btn btn-quiet" m={p.market} choice={called[0] ?? p.market.choices[i] ?? `Outcome ${i + 1}`}
          stake={formatUnits(p.stakes[i], USDC_DECIMALS, 6)} confirmedAt={null} txRef={null} account={accountId}
          result={{ status: predictionStatus(p), outcome: p.winning_choice, evidenceHash: p.evidence_hash, marketId: p.market_id }} /> : null
      })()}
      {p.claim_state === 'claimable' && (
        <button className="btn btn-primary" onClick={claim} disabled={!!busy}>{busy ? 'Waiting for wallet…' : 'Claim payout'}</button>
      )}
      {msg && (
        <p className={`fine${msg.err ? ' err' : ''}`} role="status" style={{ gridColumn: '1 / -1' }}>
          {msg.text} {msg.hash && <a className="link" href={explorerTx(msg.hash)} target="_blank" rel="noreferrer">View transaction</a>}
        </p>
      )}
    </div>
  )
}
