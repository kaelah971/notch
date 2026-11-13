import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, ExternalLink } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market, Position } from '../api/types'
import { cleanQuestion, formatUnits, USDC_DECIMALS } from '../api/format'
import { PREDICTION_STATUS_HELP, PREDICTION_STATUS_LABEL, predictionBadgeClass, predictionStatus, shortEvidence, summarizeForecast } from '../api/predictions'
import { isOpenForEntry, marketTitle } from '../components/market'
import { ErrorState, SkeletonList } from '../components/States'
import { explorerAccount } from '../wallet/WalletProvider'
import { ShareCallButton } from '../share/ShareButtons'
import { getFollowing, isNearAccount, toggleFollow } from './follows'
import './Signals.css'

/** A call = the side(s) an account has stake on. Read from the contract; nothing inferred. */
function sides(p: Position, m: Market | undefined) {
  return p.stakes.map((s, i) => ({ i, choice: m?.choices[i] ?? `Outcome ${i + 1}`, stake: s })).filter((x) => x.stake !== '0')
}

function PassportStat({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="passport-stat"><p>{label}</p><strong>{value}</strong><span>{note}</span></div>
}

function ForecastPassport({ summary }: { summary: ReturnType<typeof summarizeForecast> }) {
  const accuracy = summary.accuracy == null ? 'Unavailable' : `${Number(summary.accuracy.toFixed(1))}%`
  return (
    <section className="passport" aria-labelledby="passport-h">
      <div className="passport-head">
        <div><h2 id="passport-h" className="msec-h">Forecast passport</h2><p>Market-level accuracy from finalized contract outcomes.</p></div>
        <span className="fine">Historical demonstrations excluded</span>
      </div>
      <div className="passport-grid">
        <PassportStat label="Recorded predictions" value={String(summary.total)} note="one per market" />
        <PassportStat label="Accuracy" value={accuracy} note={`n=${summary.completed} completed`} />
        <PassportStat label="Correct" value={String(summary.correct)} note="completed predictions" />
        <PassportStat label="Incorrect" value={String(summary.incorrect)} note="completed predictions" />
        <PassportStat label="Pending" value={String(summary.pending)} note="not finalized" />
        <PassportStat label="Voided" value={String(summary.voided)} note="excluded from accuracy" />
        {summary.unknown > 0 && <PassportStat label="Unavailable" value={String(summary.unknown)} note="evidence incomplete" />}
      </div>
    </section>
  )
}

export function Predictor() {
  const { accountId = '' } = useParams()
  const valid = isNearAccount(accountId)
  const [state, reload] = useApi(() => valid
    ? Promise.all([api.positions(accountId), api.markets()]).then(([p, m]) => ({ positions: p.data, markets: new Map(m.data.map((x) => [x.market_id, x])) }))
    : Promise.reject(new Error('invalid')), [accountId])
  const [following, setFollowingState] = useState(() => getFollowing().includes(accountId))

  if (!valid) return <div className="state"><h2>Not a NEAR account ID</h2><p>Check the address and try again.</p></div>

  const passport = state.status === 'ok'
    ? summarizeForecast(state.data.positions.filter((p) => !state.data.markets.get(p.market_id)?.is_historical_replay))
    : null
  const ordered = state.status === 'ok'
    ? [...state.data.positions].sort((a, b) => {
      const at = state.data.markets.get(a.market_id)?.resolved_at_utc ?? state.data.markets.get(a.market_id)?.close_at_utc ?? ''
      const bt = state.data.markets.get(b.market_id)?.resolved_at_utc ?? state.data.markets.get(b.market_id)?.close_at_utc ?? ''
      return (Date.parse(bt) || 0) - (Date.parse(at) || 0)
    })
    : []

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
      {state.status === 'ok' && passport && (
        <>
          <ForecastPassport summary={passport} />
          {state.data.positions.length === 0
            ? <div className="state"><h2>No calls yet</h2><p>This account has no positions in Notch markets.</p></div>
            : (
              <section aria-labelledby="recent-calls-h">
                <div className="msec-hrow"><h2 id="recent-calls-h" className="msec-h">Recent prediction outcomes</h2></div>
                <div className="plist">
                  {ordered.map((p) => {
                    const m = state.data.markets.get(p.market_id)
                    const open = m ? isOpenForEntry(m) : false
                    const called = sides(p, m)
                    const result = predictionStatus(p)
                    return (
                      <div key={p.market_id} className="call">
                        <div className="call-main">
                          <div className="call-tags">
                            {m?.is_historical_replay && <span className="badge badge-replay">Resolved demonstration · not counted</span>}
                            {open ? <span className="badge badge-live">Open</span> : <span className="badge">{p.market_status}</span>}
                            <span className={`badge ${predictionBadgeClass(result)}`} title={PREDICTION_STATUS_HELP[result]}>{PREDICTION_STATUS_LABEL[result]}</span>
                            {p.winning_choice && <span className="dim">Final outcome {p.winning_choice}</span>}
                            {shortEvidence(p.evidence_hash) && <span className="mono dim">Evidence {shortEvidence(p.evidence_hash)}</span>}
                          </div>
                          <Link to={`/app/markets/${encodeURIComponent(p.market_id)}`} className="call-title">{m ? marketTitle(m) : cleanQuestion(p.question)}</Link>
                          <p className="call-sides">
                            {called.length ? called.map((s) => <span key={s.i}>Called <strong>{s.choice}</strong> · {formatUnits(s.stake, USDC_DECIMALS)} test-USDC</span>) : <span>Original call unavailable</span>}
                          </p>
                        </div>
                        <div className="call-actions">
                          {m && called.length === 1 && <ShareCallButton className="btn btn-quiet" m={m} choice={called[0].choice} stake={formatUnits(called[0].stake, USDC_DECIMALS, 6)} confirmedAt={null} txRef={null} account={accountId}
                            result={{ status: result, outcome: p.winning_choice, evidenceHash: p.evidence_hash, marketId: p.market_id }} />}
                          {open && called.map((s) => (
                            <Link key={s.i} className="btn btn-primary" to={`/app/markets/${encodeURIComponent(p.market_id)}?call=${s.i}&via=${encodeURIComponent(accountId)}`}>
                              Make the same call
                            </Link>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            )}
        </>
      )}
      <p className="fine" style={{ marginTop: 20 }}>Accuracy uses one market-level record per market and only Correct/Incorrect results. Pending, voided, unavailable, and historical demonstration positions do not inflate the rate.</p>
    </>
  )
}
