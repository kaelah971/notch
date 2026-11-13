import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronRight, Search } from 'lucide-react'
import { useWallet } from '../wallet/WalletProvider'
import { getFollowing, isNearAccount } from './follows'
import './Signals.css'

/**
 * Notch Signals V1 — look up any account's verified onchain calls, follow on this device,
 * and make the same call yourself. No rankings, profiles or follower counts are shown
 * because none are verified or persisted yet.
 */
export function SignalsHub() {
  const nav = useNavigate()
  const { accountId } = useWallet()
  const [q, setQ] = useState('')
  const following = getFollowing()
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

      <section className="msec" aria-labelledby="lb-h">
        <div className="msec-hrow"><h2 id="lb-h" className="msec-h">Leaderboard</h2></div>
        <p className="msec-empty">
          <strong className="txt">No verified rankings yet.</strong> Rankings need resolved future-outcome markets, an onchain entry index to discover predictors, and opt-in public profiles. Historical demonstrations never count. Until then, Notch shows no ranks, win rates or follower counts.
        </p>
      </section>
    </>
  )
}
