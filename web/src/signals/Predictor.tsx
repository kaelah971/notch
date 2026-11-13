import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, ExternalLink } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market, Position } from '../api/types'
import { cleanQuestion, formatUnits, USDC_DECIMALS } from '../api/format'
import { isOpenForEntry, marketTitle } from '../components/market'
import { ErrorState, SkeletonList } from '../components/States'
import { explorerAccount } from '../wallet/WalletProvider'
import { getFollowing, isNearAccount, toggleFollow } from './follows'
import './Signals.css'

/** A call = the side(s) an account has stake on. Read from the contract; nothing inferred. */
function sides(p: Position, m: Market | undefined) {
  return p.stakes.map((s, i) => ({ i, choice: m?.choices[i] ?? `Outcome ${i + 1}`, stake: s })).filter((x) => x.stake !== '0')
}

export function Predictor() {
  const { accountId = '' } = useParams()
  const valid = isNearAccount(accountId)
  const [state, reload] = useApi(() => valid
    ? Promise.all([api.positions(accountId), api.markets()]).then(([p, m]) => ({ positions: p.data, markets: new Map(m.data.map((x) => [x.market_id, x])) }))
    : Promise.reject(new Error('invalid')), [accountId])
  const [following, setFollowingState] = useState(() => getFollowing().includes(accountId))

  if (!valid) return <div className="state"><h2>Not a NEAR account ID</h2><p>Check the address and try again.</p></div>

  return (
    <>
      <Link to="/app/leaderboard" className="md-back"><ChevronLeft size={18} /> Signals</Link>
      <header className="page-head">
        <div>
          <h1 className="pred-name">{accountId}</h1>
          <p>Calls read from the NEAR Testnet market contract · <a className="link" href={explorerAccount(accountId)} target="_blank" rel="noreferrer">All transactions <ExternalLink size={13} /></a></p>
        </div>
        <button className={`btn ${following ? 'btn-quiet' : 'btn-primary'}`} aria-pressed={following}
          onClick={() => setFollowingState(toggleFollow(accountId))}>{following ? 'Following' : 'Follow'}</button>
      </header>
      <p className="fine" style={{ marginTop: -12, marginBottom: 20 }}>Follows are saved on this device only. Onchain positions are public; this page shows only what the contract returns for this account.</p>

      {state.status === 'loading' && <SkeletonList n={2} h={110} />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (state.data.positions.length === 0
        ? <div className="state"><h2>No calls yet</h2><p>This account has no positions in Notch markets.</p></div>
        : (
          <div className="plist">
            {state.data.positions.map((p) => {
              const m = state.data.markets.get(p.market_id)
              const open = m ? isOpenForEntry(m) : false
              return (
                <div key={p.market_id} className="call">
                  <div className="call-main">
                    <div className="call-tags">
                      {m?.is_historical_replay && <span className="badge badge-replay">Resolved demonstration · not counted</span>}
                      {open ? <span className="badge badge-live">Open</span> : <span className="badge">{p.market_status}</span>}
                      {p.winning_choice && <span className="dim">Outcome {p.winning_choice}</span>}
                    </div>
                    <Link to={`/app/markets/${encodeURIComponent(p.market_id)}`} className="call-title">{m ? marketTitle(m) : cleanQuestion(p.question)}</Link>
                    <p className="call-sides">
                      {sides(p, m).map((s) => <span key={s.i}>Called <strong>{s.choice}</strong> · {formatUnits(s.stake, USDC_DECIMALS)} test-USDC</span>)}
                    </p>
                  </div>
                  {open && sides(p, m).map((s) => (
                    <Link key={s.i} className="btn btn-primary" to={`/app/markets/${encodeURIComponent(p.market_id)}?call=${s.i}&via=${encodeURIComponent(accountId)}`}>
                      Make the same call
                    </Link>
                  ))}
                </div>
              )
            })}
          </div>
        ))}
      <p className="fine" style={{ marginTop: 20 }}>“Make the same call” only preselects the market and side. You choose your own stake and approve it in your own wallet. Payouts depend on the pool when the market resolves, so your result can differ.</p>
    </>
  )
}
