import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { EntryIntent, MarketDetail, Readiness } from '../api/types'
import { formatUnits, parseUnits, relativeTo, USDC_DECIMALS } from '../api/format'
import { isOpenForEntry } from '../components/market'
import { ShareCallButton } from '../share/ShareButtons'
import { explorerTx, useWallet } from '../wallet/WalletProvider'
import { clearPending, consumeRedirectParams, loadPending, savePending, stakeIn, waitForStakeIncrease } from '../wallet/verify'

type Phase =
  | { k: 'idle' }
  | { k: 'preparing' }
  | { k: 'review'; intent: EntryIntent; before: string }
  | { k: 'signing'; intent: EntryIntent }
  | { k: 'verifying'; hash: string | null; choice: string; stake: string }
  | { k: 'confirmed'; hash: string | null; choice: string; stake: string; total: string; at: string }
  | { k: 'unconfirmed'; hash: string | null }
  | { k: 'error'; message: string }

export function EntryPanel({ d, onPositionChange }: { d: MarketDetail; onPositionChange?: () => void }) {
  const { accountId, connect, ready, signAndSend } = useWallet()
  // Notch Signals "Make the same call": ?call=<outcome index>&via=<account>. Preselects only; stake and signature are the user's.
  const [params] = useSearchParams()
  const callParam = Number(params.get('call'))
  const via = params.get('via')
  const preset = Number.isInteger(callParam) && callParam >= 0 && callParam < d.choices.length ? callParam : null
  const [side, setSide] = useState<number | null>(preset)
  const [amount, setAmount] = useState('')
  const [phase, setPhase] = useState<Phase>({ k: 'idle' })
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [readinessErr, setReadinessErr] = useState<string | null>(null)
  const [regBusy, setRegBusy] = useState(false)

  const min = d.contract_config?.min_entry_amount ?? '1000000'
  const collateral = d.contract_config?.collateral_token ?? 'usdc.tidepool-sandbox.testnet'

  // Readiness (balance + storage) for the connected account.
  const loadReadiness = () => {
    if (!accountId) { setReadiness(null); return }
    setReadinessErr(null)
    api.readiness(accountId).then((r) => setReadiness(r.data), (e: ApiError) => setReadinessErr(e.message))
  }
  useEffect(loadReadiness, [accountId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Returning from a redirect wallet: verify against the contract, never trust the URL alone.
  useEffect(() => {
    const ret = consumeRedirectParams()
    if (!ret) return
    const pending = loadPending(d.market_id)
    if (ret.error) { clearPending(); setPhase({ k: 'error', message: 'The wallet did not send the transaction.' }); return }
    if (!pending) return
    const hash = ret.hashes.at(-1) ?? null
    setPhase({ k: 'verifying', hash, choice: pending.choice, stake: pending.stake })
    waitForStakeIncrease(pending.accountId, d.market_id, pending.before).then((total) => {
      clearPending()
      if (total) { setPhase({ k: 'confirmed', hash, choice: pending.choice, stake: pending.stake, total, at: new Date().toISOString() }); onPositionChange?.() }
      else setPhase({ k: 'unconfirmed', hash })
    })
  }, [d.market_id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!isOpenForEntry(d)) {
    return (
      <section className="card entry">
        <h2 className="card-h">Entries closed</h2>
        <p className="dim">{d.winning_choice ? <>Resolved outcome: <strong className="txt">{d.winning_choice}</strong></> : 'This market is not accepting entries.'}</p>
      </section>
    )
  }

  const stake = parseUnits(amount, USDC_DECIMALS)
  const belowMin = stake != null && BigInt(stake) < BigInt(min)
  const overBalance = stake != null && readiness != null && BigInt(stake) > BigInt(readiness.balance)
  const canReview = !!accountId && side != null && stake != null && !belowMin && !overBalance && readiness?.storage_registered === true

  async function review() {
    if (!accountId || side == null || !stake) return
    setPhase({ k: 'preparing' })
    try {
      const [intent, before] = await Promise.all([
        api.entryIntent(d.market_id, { account_id: accountId, side, stake }).then((r) => r.data),
        stakeIn(accountId, d.market_id),
      ])
      if (intent.signer !== accountId || intent.args.receiver_id === undefined) throw new Error('Intent does not match the connected account.')
      setPhase({ k: 'review', intent, before })
    } catch (e) {
      setPhase({ k: 'error', message: e instanceof Error ? e.message : String(e) })
    }
  }

  async function sign(intent: EntryIntent, before: string) {
    if (!accountId) return
    setPhase({ k: 'signing', intent })
    savePending({ marketId: d.market_id, accountId, before, choice: intent.choice, stake: intent.stake, at: Date.now() })
    try {
      const res = await signAndSend({
        receiverId: intent.receiver,
        calls: [{ methodName: intent.method, args: intent.args, gasTgas: intent.gas_tgas, depositYocto: intent.attached_deposit_yocto }],
      })
      if (res.redirected) return // page navigates to the wallet; verification resumes on return
      setPhase({ k: 'verifying', hash: res.hash, choice: intent.choice, stake: intent.stake })
      const total = await waitForStakeIncrease(accountId, d.market_id, before)
      clearPending()
      if (total) { setPhase({ k: 'confirmed', hash: res.hash, choice: intent.choice, stake: intent.stake, total, at: new Date().toISOString() }); onPositionChange?.(); loadReadiness() }
      else setPhase({ k: 'unconfirmed', hash: res.hash })
    } catch (e) {
      clearPending()
      setPhase({ k: 'error', message: e instanceof Error ? e.message : 'The wallet rejected or failed the transaction.' })
    }
  }

  async function registerStorage() {
    if (!accountId) return
    setRegBusy(true)
    try {
      // NEP-145 registration on the collateral token, signed by the user. Typical cost 0.00125 NEAR.
      await signAndSend({ receiverId: collateral, calls: [{ methodName: 'storage_deposit', args: { account_id: accountId, registration_only: true }, gasTgas: 30, depositYocto: '1250000000000000000000' }] })
      loadReadiness()
    } catch (e) {
      setReadinessErr(e instanceof Error ? e.message : String(e))
    } finally { setRegBusy(false) }
  }

  // --- Terminal / in-flight states -------------------------------------------------
  if (phase.k === 'review' || phase.k === 'signing') {
    const it = phase.intent
    return (
      <section className="card entry">
        <h2 className="card-h">Review your position</h2>
        <dl className="kv kv-tight">
          <div><dt>Call</dt><dd><strong className="txt">{it.choice}</strong></dd></div>
          <div><dt>Your stake</dt><dd className="mono">{formatUnits(it.stake, USDC_DECIMALS, 6)} test-USDC</dd></div>
          <div><dt>Signer</dt><dd className="mono">{it.signer}</dd></div>
          <div><dt>Contract</dt><dd className="mono">{it.receiver}</dd></div>
          <div><dt>Method</dt><dd className="mono">{it.method} → {it.args.receiver_id}</dd></div>
          <div><dt>Deposit / gas</dt><dd className="mono">{it.attached_deposit_yocto} yocto · {it.gas_tgas} Tgas</dd></div>
          <div><dt>Protocol fee</dt><dd>{((Number(d.contract_config?.fee_bps ?? 0)) / 100).toFixed(2)}%</dd></div>
        </dl>
        <Payout d={d} outcome={it.outcome} stake={it.stake} choice={it.choice} />
        <p className="fine">Your wallet will show this exact transaction. Notch cannot sign or move funds for you.</p>
        <button className="btn btn-primary w100" onClick={() => phase.k === 'review' && sign(it, phase.before)} disabled={phase.k === 'signing'}>
          {phase.k === 'signing' ? 'Waiting for wallet…' : 'Sign in wallet'}
        </button>
        <button className="btn btn-ghost w100" onClick={() => setPhase({ k: 'idle' })} disabled={phase.k === 'signing'}>Edit</button>
      </section>
    )
  }
  if (phase.k === 'verifying') {
    return (
      <section className="card entry" aria-live="polite">
        <h2 className="card-h">Confirming onchain</h2>
        <p className="dim">Reading your position from the market contract…</p>
        {phase.hash && <a className="link" href={explorerTx(phase.hash)} target="_blank" rel="noreferrer">View transaction</a>}
      </section>
    )
  }
  if (phase.k === 'confirmed') {
    return (
      <section className="card entry" aria-live="polite">
        <h2 className="card-h">Position confirmed</h2>
        <p>You called <strong>{phase.choice}</strong> with {formatUnits(phase.stake, USDC_DECIMALS, 6)} test-USDC.</p>
        <p className="fine">Your total stake in this market is now {formatUnits(phase.total, USDC_DECIMALS, 6)} test-USDC, as read from the contract.</p>
        {phase.hash && <a className="link" href={explorerTx(phase.hash)} target="_blank" rel="noreferrer">View transaction</a>}
        {accountId && <div className="row-gap"><ShareCallButton m={d} choice={phase.choice} stake={formatUnits(phase.stake, USDC_DECIMALS, 6)} confirmedAt={phase.at} txRef={phase.hash} account={accountId} /></div>}
        <div className="row-gap"><Link to="/app/portfolio" className="btn btn-quiet">Your positions</Link><button className="btn btn-ghost" onClick={() => setPhase({ k: 'idle' })}>Stake more</button></div>
      </section>
    )
  }
  if (phase.k === 'unconfirmed') {
    return (
      <section className="card entry" aria-live="polite">
        <h2 className="card-h">Not confirmed yet</h2>
        <p className="dim">The contract does not show a new stake for this account. The transaction may have been refunded or is still finalising. Check the explorer before trying again.</p>
        {phase.hash && <a className="link" href={explorerTx(phase.hash)} target="_blank" rel="noreferrer">View transaction</a>}
        <button className="btn btn-quiet w100" onClick={() => setPhase({ k: 'idle' })}>Back</button>
      </section>
    )
  }

  // --- Form ---------------------------------------------------------------------------
  return (
    <section className="card entry">
      <h2 className="card-h">Make your call</h2>
      {preset != null && via && (
        <div className="notice referral-notice" role="note">
          <span className="referral-lead">Following <Link className="link referral-account" to={`/app/p/${encodeURIComponent(via)}`}>{via}</Link>&apos;s call</span>
          <strong className="referral-side">{d.choices[preset]}</strong>
          <span className="referral-hint">Choose your own stake</span>
        </div>
      )}
      <div className="entry-choices" role="radiogroup" aria-label="Choose an outcome">
        {d.choices.map((c, i) => (
          <button key={c} role="radio" aria-checked={side === i} className={`choice${side === i ? ' is-on' : ''}`} onClick={() => setSide(i)}>{c}</button>
        ))}
      </div>

      <label className="field">
        <span>Stake test-USDC</span>
        <div className="field-in">
          <input inputMode="decimal" autoComplete="off" placeholder={formatUnits(min, USDC_DECIMALS)} value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))} aria-invalid={belowMin || overBalance || (amount !== '' && stake == null)} />
          <span className="dim">USDC</span>
        </div>
      </label>
      <p className="fine">
        {amount !== '' && stake == null ? 'Enter a valid amount (max 6 decimals).'
          : belowMin ? `Minimum entry is ${formatUnits(min, USDC_DECIMALS)} test-USDC.`
          : overBalance ? 'Stake is more than your test-USDC balance.'
          : `Minimum ${formatUnits(min, USDC_DECIMALS)} test-USDC · entries close ${relativeTo(d.close_at_utc)}`}
      </p>

      {!accountId ? (
        <button className="btn btn-primary w100" onClick={connect} disabled={!ready}>Connect wallet to enter</button>
      ) : (
        <>
          {readiness && (
            <p className="fine">Balance <span className="mono txt">{formatUnits(readiness.balance, USDC_DECIMALS, 6)}</span> test-USDC</p>
          )}
          {readiness && !readiness.storage_registered && (
            <div className="notice">
              <p>Your account isn’t registered on the test-USDC token yet. Registration costs 0.00125 NEAR and is signed by you.</p>
              <button className="btn btn-quiet" onClick={registerStorage} disabled={regBusy}>{regBusy ? 'Waiting for wallet…' : 'Register test-USDC'}</button>
            </div>
          )}
          {readiness?.storage_registered && BigInt(readiness.balance) < BigInt(min) && (
            <div className="notice"><p>You need at least {formatUnits(min, USDC_DECIMALS)} test-USDC.</p><Link className="btn btn-quiet" to="/app/portfolio#fund">Get test-USDC</Link></div>
          )}
          {readinessErr && <p className="fine err">{readinessErr}</p>}
          <button className="btn btn-primary w100" onClick={review} disabled={!canReview || phase.k === 'preparing'}>
            {phase.k === 'preparing' ? 'Preparing…' : 'Take a position'}
          </button>
        </>
      )}
      {phase.k === 'error' && <p className="fine err" role="alert">{phase.message}</p>}
    </section>
  )
}

/** Parimutuel payout mechanics from the contract: stake × escrow_total ÷ winning pool. */
function Payout({ d, outcome, stake, choice }: { d: MarketDetail; outcome: number; stake: string; choice: string }) {
  const s = BigInt(stake)
  const total = d.totals.reduce((a, b) => a + BigInt(b), 0n) + s
  const side = BigInt(d.totals[outcome] ?? '0') + s
  const now = side > 0n ? (s * total) / side : 0n
  return (
    <div className="notice">
      <p><strong className="txt">If {choice} wins</strong>, your payout is your stake × total pool ÷ {choice} pool, measured when the market resolves. If the market is voided, your stake is refunded. If {choice} loses, you receive nothing.</p>
      <p>With today’s pools plus your stake that would be <span className="mono txt">{formatUnits(now.toString(), USDC_DECIMALS, 6)}</span> test-USDC. It will change as others enter before entries close — it is not a quote or a guarantee.</p>
    </div>
  )
}
