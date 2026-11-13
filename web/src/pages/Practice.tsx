import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../api/useApi'
import type { Market, PredictionStatus } from '../api/types'
import { cleanQuestion, formatUtc, relativeTo } from '../api/format'
import { marketCategory, marketTitle, StatusBadge } from '../components/market'
import { ErrorState, SkeletonList } from '../components/States'
import { PREDICTION_STATUS_HELP, PREDICTION_STATUS_LABEL, predictionBadgeClass } from '../api/predictions'
import { SharePracticeButton } from '../share/ShareButtons'
import {
  PRACTICE_STORAGE_KEY,
  addPracticePosition,
  getPracticeLedger,
  isPracticeReplay,
  isPracticeSelectable,
  readPracticeState,
  summarizePractice,
  writePracticeState,
  type PracticeLedger,
  type PracticeState,
} from '../practice/practice'
import './Practice.css'

const statusLabel = (status: PredictionStatus) => status === 'UNKNOWN' ? 'Unknown' : PREDICTION_STATUS_LABEL[status]
const formatCredits = (value: number) => `${value.toLocaleString('en-US')} credits`
const marketSort = (a: Market, b: Market) => Number(isPracticeReplay(a)) - Number(isPracticeReplay(b)) || Date.parse(a.close_at_utc) - Date.parse(b.close_at_utc)

export function Practice() {
  const [marketsState, reloadMarkets] = useApi(() => api.markets(), [])
  const [params, setParams] = useSearchParams()
  const [practiceState, setPracticeState] = useState<PracticeState>(() => readPracticeState())

  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === PRACTICE_STORAGE_KEY) setPracticeState(readPracticeState()) }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  const markets = marketsState.status === 'ok' ? marketsState.data.data : []
  const eligibleMarkets = markets.filter((market) => isPracticeSelectable(market)).sort(marketSort)
  const selectedId = params.get('market')
  const selectedMarket = selectedId ? markets.find((market) => market.market_id === selectedId) ?? null : null
  const ledger = getPracticeLedger(practiceState, markets)
  const summary = summarizePractice(ledger.positions)

  const selectMarket = (marketId: string) => {
    const next = new URLSearchParams(params)
    next.set('market', marketId)
    setParams(next, { replace: true })
  }
  const savePracticeState = (next: PracticeState) => {
    setPracticeState(next)
    writePracticeState(next)
  }

  return (
    <>
      <header className="page-head practice-head">
        <div>
          <p className="eyebrow">No wallet required</p>
          <h1>Practice Arena</h1>
          <p>Learn the Notch prediction loop with real published markets, without spending NEAR or test-USDC.</p>
        </div>
        <div className="practice-head-side">
          <span className="badge badge-live">Practice Mode</span>
          <Link className="btn btn-quiet" to="/app/portfolio">Real Portfolio →</Link>
        </div>
      </header>

      <section className="practice-disclosure" aria-label="Practice Mode rules">
        <div><strong>1,000 practice credits</strong><span>virtual starting budget · local to this device</span></div>
        <p>Practice calls never connect a wallet, call a signer, submit an entry intent, or create a blockchain transaction. They are separate from test-USDC positions and have no monetary value.</p>
      </section>

      {marketsState.status === 'loading' && <SkeletonList n={3} h={150} />}
      {marketsState.status === 'error' && <ErrorState error={marketsState.error} onRetry={reloadMarkets} />}
      {marketsState.status === 'ok' && (
        <>
          <div className="practice-grid">
            <MarketPicker markets={eligibleMarkets} selectedId={selectedId} onSelect={selectMarket} />
            <PracticeEntry market={selectedMarket} state={practiceState} ledger={ledger} markets={markets} onSaved={savePracticeState} />
          </div>
          <PracticePortfolio ledger={ledger} summary={summary} />
        </>
      )}
    </>
  )
}

function MarketPicker({ markets, selectedId, onSelect }: { markets: Market[]; selectedId: string | null; onSelect: (marketId: string) => void }) {
  const live = markets.filter((market) => !isPracticeReplay(market))
  const replay = markets.filter(isPracticeReplay)
  return (
    <section className="practice-panel" aria-labelledby="practice-markets-title">
      <div className="practice-panel-head">
        <div><p className="eyebrow">1 · Discover</p><h2 id="practice-markets-title">Choose a market</h2></div>
        <span className="practice-panel-note">published questions only</span>
      </div>
      <p className="practice-copy">Select an open market to make a live-looking practice call before its authoritative entry deadline. Resolved demonstrations are clearly labelled and can be replayed for learning.</p>
      {!markets.length && <div className="practice-empty"><strong>No practice market is available.</strong><p>There are no open future markets or resolved demonstration markets in the current API response.</p></div>}
      {!!live.length && <div className="practice-market-list">{live.map((market) => <MarketChoice key={market.market_id} market={market} selected={market.market_id === selectedId} onSelect={onSelect} />)}</div>}
      {!!replay.length && (
        <>
          <div className="practice-subhead"><span>Resolved demonstrations</span><small>test/demo data · not participant activity</small></div>
          <div className="practice-market-list">{replay.map((market) => <MarketChoice key={market.market_id} market={market} selected={market.market_id === selectedId} onSelect={onSelect} />)}</div>
        </>
      )}
    </section>
  )
}

function MarketChoice({ market, selected, onSelect }: { market: Market; selected: boolean; onSelect: (marketId: string) => void }) {
  return (
    <button type="button" className={`practice-market-choice${selected ? ' is-selected' : ''}`} aria-pressed={selected} onClick={() => onSelect(market.market_id)}>
      <span className="practice-market-top"><span>{marketCategory(market)}</span><StatusBadge m={market} /></span>
      <strong>{marketTitle(market)}</strong>
      <span className="practice-question">{cleanQuestion(market.question)}</span>
      <span className="practice-market-foot">
        <span>{isPracticeReplay(market) ? 'Replay resolved result' : `Closes ${relativeTo(market.close_at_utc)}`}</span>
        <span>{market.choices.join(' / ')}</span>
      </span>
    </button>
  )
}

function PracticeEntry({ market, state, ledger, markets, onSaved }: { market: Market | null; state: PracticeState; ledger: PracticeLedger; markets: Market[]; onSaved: (next: PracticeState) => void }) {
  const [choice, setChoice] = useState<number | null>(null)
  const [stake, setStake] = useState('')
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null)
  const duplicate = !!market && state.positions.some((position) => position.market_id === market.market_id)
  const selectable = !!market && isPracticeSelectable(market)
  const parsedStake = /^\d+$/.test(stake) ? Number(stake) : null

  function submit() {
    if (!market || choice == null || parsedStake == null) return
    const result = addPracticePosition(state, market, choice, parsedStake, markets)
    if (!result.validation.ok) {
      const text = result.validation.code === 'DUPLICATE_MARKET' ? 'You already have a practice call for this market.'
        : result.validation.code === 'INSUFFICIENT_CREDITS' ? 'That stake is above your available practice credits.'
          : result.validation.code === 'MARKET_CLOSED' ? 'Practice calls are closed after the market’s authoritative entry deadline.'
            : result.validation.code === 'INVALID_CHOICE' ? 'Choose one published outcome.'
              : 'Enter a whole-number practice stake greater than zero.'
      setMessage({ text, error: true })
      return
    }
    onSaved(result.state)
    setMessage({ text: `Recorded ${market.choices[choice]} for ${formatCredits(parsedStake)}. No wallet or transaction was used.` })
  }

  return (
    <section className="practice-panel practice-entry-panel" aria-labelledby="practice-entry-title">
      <div className="practice-panel-head">
        <div><p className="eyebrow">2 · Select</p><h2 id="practice-entry-title">Your practice call</h2></div>
        <span className="practice-local-label">local-only record</span>
      </div>
      {!market ? (
        <div className="practice-empty practice-entry-empty"><strong>Pick a market to begin.</strong><p>Your call will be stored only in this browser.</p></div>
      ) : (
        <>
          <div className="practice-selected-market">
            <span className="practice-market-top"><span>{isPracticeReplay(market) ? 'Resolved demonstration' : 'Live market window'}</span><StatusBadge m={market} /></span>
            <h3>{marketTitle(market)}</h3>
            <p>{cleanQuestion(market.question)}</p>
            {!selectable && !isPracticeReplay(market) && <p className="practice-error" role="alert">Practice calls are closed. The authoritative deadline has passed or this market is no longer accepting entries.</p>}
            {isPracticeReplay(market) && <p className="practice-replay-note">This is test/demo data from a resolved market. It is not a real participant call and does not affect Pulse, Passport, or rankings.</p>}
          </div>
          <div className="practice-choices" role="radiogroup" aria-label="Choose a practice outcome">
            {market.choices.map((label, index) => (
              <button key={label} type="button" role="radio" aria-checked={choice === index} className={`practice-choice${choice === index ? ' is-on' : ''}`} disabled={!selectable || duplicate} onClick={() => setChoice(index)}>{label}</button>
            ))}
          </div>
          <label className="practice-stake-field">
            <span>Practice credits to allocate</span>
            <div><input inputMode="numeric" pattern="[0-9]*" value={stake} onChange={(event) => setStake(event.target.value.replace(/[^\d]/g, ''))} placeholder="e.g. 100" aria-describedby="practice-stake-help" aria-invalid={stake !== '' && (parsedStake == null || parsedStake <= 0)} /><span>credits</span></div>
          </label>
          <p id="practice-stake-help" className="practice-help">Available: <strong>{formatCredits(ledger.available_credits)}</strong> · one practice call per market · no pool payout simulation.</p>
          {duplicate && <div className="practice-notice"><strong>Already practised.</strong><span>This device already has a call for this market. View it below instead of submitting a duplicate.</span><a href="#practice-portfolio">View practice portfolio</a></div>}
          {message && <p className={`practice-message${message.error ? ' practice-error' : ''}`} role={message.error ? 'alert' : 'status'}>{message.text}</p>}
          <button type="button" className="btn btn-primary w100" onClick={submit} disabled={!selectable || duplicate || choice == null || parsedStake == null || parsedStake <= 0}>Record practice call</button>
          <p className="practice-no-wallet">No signer · no entry-intent request · no transaction · no test-USDC.</p>
        </>
      )}
    </section>
  )
}

function PracticePortfolio({ ledger, summary }: { ledger: PracticeLedger; summary: ReturnType<typeof summarizePractice> }) {
  const ordered = [...ledger.positions].sort((a, b) => Date.parse(b.created_at_utc) - Date.parse(a.created_at_utc))
  return (
    <section className="practice-portfolio" id="practice-portfolio" aria-labelledby="practice-portfolio-title">
      <div className="practice-portfolio-head">
        <div><p className="eyebrow">3 · Review</p><h2 id="practice-portfolio-title">Practice Portfolio</h2></div>
        <span className="practice-local-label">saved on this device only</span>
      </div>
      <div className="practice-stats" aria-label="Practice performance summary">
        <PracticeStat label="Available" value={formatCredits(ledger.available_credits)} />
        <PracticeStat label="Reserved" value={formatCredits(ledger.reserved_credits)} />
        <PracticeStat label="Total calls" value={String(summary.total)} />
        <PracticeStat label="Correct" value={String(summary.correct)} />
        <PracticeStat label="Incorrect" value={String(summary.incorrect)} />
        <PracticeStat label="Pending" value={String(summary.pending)} />
        <PracticeStat label="Voided" value={String(summary.voided)} />
        <PracticeStat label="Unknown" value={String(summary.unknown)} />
      </div>
      <div className="practice-performance-line">
        <strong>{summary.accuracy == null ? 'Accuracy unavailable' : `${summary.accuracy.toFixed(1)}% accuracy`}</strong>
        <span>{summary.completed ? `n=${summary.completed} completed Correct/Incorrect calls` : 'Complete a finalized call to establish an accuracy sample.'}</span>
        <span>Streak: {summary.current_streak} current · {summary.best_streak} best</span>
      </div>
      <p className="practice-scoring-note"><strong>Practice scoring:</strong> Correct returns the stake plus an equal virtual reward; Incorrect spends the stake; Voided refunds it; Pending and Unknown remain reserved. This is a simple learning score, not a reproduction of pool payouts, profit, or test-USDC.</p>
      {!ordered.length ? <div className="practice-empty"><strong>No practice calls yet.</strong><p>Choose a published market above to create your first walletless position.</p></div> : (
        <div className="practice-position-list">
          {ordered.map((position) => <PracticePositionRow key={position.market_id} position={position} />)}
        </div>
      )}
      <p className="practice-footnote">Local-only storage can be cleared by browser settings, is not synced between devices, and is not evidence of an onchain position. Practice records never enter Pulse, Passport, Social Discovery, or verified trader rankings.</p>
    </section>
  )
}

function PracticeStat({ label, value }: { label: string; value: string }) {
  return <div className="practice-stat"><span>{label}</span><strong>{value}</strong></div>
}

function PracticePositionRow({ position }: { position: PracticeLedger['positions'][number] }) {
  const title = position.market ? marketTitle(position.market) : position.market_question
  const status = position.status
  const help = PREDICTION_STATUS_HELP[status]
  const explanation = status === 'PENDING' ? 'Market not finalized yet.'
    : status === 'CORRECT' ? `Final outcome: ${position.outcome ?? 'unavailable'}.`
      : status === 'INCORRECT' ? `Final outcome: ${position.outcome ?? 'unavailable'}.`
        : status === 'VOIDED' ? 'Market voided; practice stake refunded.'
          : 'Finalized outcome or evidence is unavailable; no result is claimed.'
  return (
    <article className="practice-position-row">
      <div className="practice-position-main">
        <div className="practice-position-top"><time dateTime={position.created_at_utc}>{formatUtc(position.created_at_utc)}</time><span className={`badge ${predictionBadgeClass(status)}`} title={help}>{statusLabel(status)}</span></div>
        {position.market ? <Link to={`/app/markets/${encodeURIComponent(position.market.market_id)}`} className="practice-position-title">{title}</Link> : <strong className="practice-position-title">{title}</strong>}
        <p className="practice-position-call">Called <strong>{position.choice}</strong> · {formatCredits(position.stake)} · {explanation}</p>
      </div>
      {position.market && <SharePracticeButton className="btn btn-quiet practice-share" m={position.market} choice={position.choice} stake={String(position.stake)} result={{ status, outcome: position.outcome, evidenceHash: position.market.evidence_hash, marketId: position.market.market_id }} />}
    </article>
  )
}
