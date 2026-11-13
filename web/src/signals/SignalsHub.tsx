import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronRight, Search } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import { ErrorState, SkeletonList } from '../components/States'
import { useWallet } from '../wallet/WalletProvider'
import { getFollowing, isNearAccount } from './follows'
import { PassportLeaderboard } from './Discovery'
import './Signals.css'

/**
 * Notch Signals V1 — look up any account's verified onchain calls, follow on this device,
 * and make the same call yourself. Forecast passports are derived only from finalized
 * market outcomes; rankings and follower counts are not shown.
 */
export function SignalsHub() {
  const nav = useNavigate()
  const { accountId } = useWallet()
  const [q, setQ] = useState('')
  const following = getFollowing()
  const [pulseState, reloadPulse] = useApi(() => api.pulse('all', false), [])
  const [marketsState] = useApi(() => api.markets(), [])
  const valid = isNearAccount(q.trim().toLowerCase())

  return (
    <>
      <header className="page-head">
        <div><h1>Signals</h1><p>Follow the insight. Make your own call.</p></div>
      </header>

      <form className="sig-search" onSubmit={(e) => { e.preventDefault(); if (valid) nav(`/app/p/${encodeURIComponent(q.trim().toLowerCase())}`) }}>
        <label className="msearch">
          <Search size={18} aria-hidden />
          <input placeholder="Look up a predictor by NEAR account, e.g. name.testnet" value={q} onChange={(e) => setQ(e.target.value)} aria-label="NEAR account ID" autoCapitalize="none" spellCheck={false} />
        </label>
        <button className="btn btn-primary" disabled={!valid}>View calls</button>
      </form>

      <section className="msec" aria-labelledby="fol-h">
        <div className="msec-hrow"><h2 id="fol-h" className="msec-h">Following</h2><span className="msec-hint">Saved on this device</span></div>
        {following.length
          ? <ul className="ilist">{following.map((id) => <li key={id}><Link className="irow" to={`/app/p/${encodeURIComponent(id)}`}><span className="mono">{id}</span><ChevronRight size={18} className="dim" /></Link></li>)}</ul>
          : <p className="msec-empty">You’re not following anyone yet. Look up an account above, or open a shared Call Card.</p>}
      </section>

      {accountId && (
        <section className="msec">
          <div className="msec-hrow"><h2 className="msec-h">Your calls</h2></div>
          <Link className="irow ilist" to={`/app/p/${encodeURIComponent(accountId)}`}><span className="mono">{accountId}</span><ChevronRight size={18} className="dim" /></Link>
        </section>
      )}

      {pulseState.status === 'loading' && <SkeletonList n={3} h={72} />}
      {pulseState.status === 'error' && <ErrorState error={pulseState.error} onRetry={reloadPulse} />}
      {pulseState.status === 'ok' && marketsState.status === 'ok' && (
        <PassportLeaderboard participants={pulseState.data.data.participants} markets={marketsState.data.data} coverage={pulseState.data.data.coverage} />
      )}
      {pulseState.status === 'ok' && marketsState.status === 'error' && (
        <section className="msec"><p className="msec-empty">Leaderboard needs the public market catalogue to classify Passport results. Try again when the read-only API is available.</p></section>
      )}
    </>
  )
}
