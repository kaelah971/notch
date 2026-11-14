import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Bot, Check, Database, ExternalLink, Info, Play, RefreshCw, ShieldCheck, SlidersHorizontal, Trophy, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import { NVIDIA_MOMENTUM_DATASET } from '../practice/fixtures/nvidia-momentum-v1'
import { readStrategies, type StrategyDefinition } from '../strategy/strategy'
import {
  ARENA_DEFAULT_RISK_POLICY,
  arenaParticipants,
  runArenaMatch,
  type ArenaDecisionRecord,
  type ArenaMatch,
  type ArenaParticipant,
  type ArenaParticipantResult,
} from '../arena/arena'
import './Arena.css'

const formatCredits = (value: number) => `${value.toLocaleString('en-US')} credits`
const percent = (value: number | null) => value == null ? '—' : `${value.toFixed(1)}%`
const compactHash = (value: string) => value.length > 22 ? `${value.slice(0, 14)}…${value.slice(-6)}` : value

export function Arena() {
  const [savedStrategies, setSavedStrategies] = useState<StrategyDefinition[]>(() => readStrategies())
  const [savedId, setSavedId] = useState('')
  const [selectedIds, setSelectedIds] = useState<string[]>(() => [
    'bot_attention_momentum_v1',
    'bot_contrarian_reversal_v1',
    'baseline_always_up_v1',
    'baseline_always_down_v1',
  ])
  const [match, setMatch] = useState<ArenaMatch | null>(null)
  const [inspectId, setInspectId] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'notch.strategy.builder.v1') setSavedStrategies(readStrategies())
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  const savedStrategy = savedStrategies.find((strategy) => strategy.strategy_id === savedId) ?? null
  const participantSet = useMemo(() => arenaParticipants(savedStrategy), [savedStrategy])
  const selectedParticipants = participantSet.participants.filter((participant) => selectedIds.includes(participant.participant_id))
  const inspectedResult = match?.results.find((result) => result.participant_id === inspectId) ?? match?.results.find((result) => result.participant_id === match.leaderboard[0]?.participant_id) ?? match?.results[0] ?? null

  function selectSavedStrategy(strategyId: string) {
    setSavedId(strategyId)
    setMatch(null)
    if (!strategyId) {
      setSelectedIds((current) => current.filter((id) => !id.startsWith('saved_')))
      return
    }
    const participantId = `saved_${strategyId}`
    setSelectedIds((current) => [...current.filter((id) => !id.startsWith('saved_')), participantId])
  }

  function toggleParticipant(participantId: string) {
    setMatch(null)
    setMessage(null)
    setSelectedIds((current) => current.includes(participantId) ? current.filter((id) => id !== participantId) : [...current, participantId])
  }

  function runMatch() {
    if (selectedParticipants.length < 2) {
      setMessage('Select at least two participants so the leaderboard has a comparison population.')
      return
    }
    const next = runArenaMatch(NVIDIA_MOMENTUM_DATASET, selectedParticipants, { excluded_participants: participantSet.excluded })
    setMatch(next)
    setInspectId(next.leaderboard[0]?.participant_id ?? next.results[0]?.participant_id ?? '')
    setMessage(null)
  }

  return (
    <div className="arena-page">
      <header className="page-head arena-head">
        <div>
          <Link className="arena-back" to="/app/strategy-lab"><ArrowLeft size={16} aria-hidden="true" /> Strategy Evaluation Lab</Link>
          <p className="eyebrow">PHASE 6A / AGENT ARENA V1</p>
          <h1>Agent Arena</h1>
          <p>Compare deterministic forecasting strategies on the same frozen Wikimedia evidence before considering real on-chain participation.</p>
        </div>
        <div className="arena-head-badge"><ShieldCheck size={15} aria-hidden="true" />Walletless · historical only</div>
      </header>

      <section className="arena-hero-note" aria-label="Arena boundary">
        <div><strong>Controlled competition, not autonomous trading</strong><span>Every participant is deterministic, versioned and evidence-bounded.</span></div>
        <p>No fake identities, live AI agents, wallet calls, entries, contract changes or transactions are used. Virtual credits have no USDC value.</p>
      </section>

      <section className="arena-panel" aria-labelledby="arena-choose-title">
        <div className="arena-panel-head"><div><p className="eyebrow">1 · Choose strategies</p><h2 id="arena-choose-title">Build the participant field</h2></div><span className="arena-panel-note">same dataset · same cutoffs</span></div>
        <p className="arena-copy">Arena V1 supplies every participant with the same complete-window candidates. Built-ins are labeled deterministic strategy bots or baselines; a saved strategy is included only when it matches the fixed Nvidia 7-day / 7-day methodology.</p>
        <div className="arena-participant-grid">
          {participantSet.participants.map((participant) => <ParticipantChoice key={participant.participant_id} participant={participant} selected={selectedIds.includes(participant.participant_id)} onToggle={() => toggleParticipant(participant.participant_id)} />)}
        </div>
        {participantSet.excluded.map((item) => <div className="arena-excluded" key={item.participant_id}><Info size={15} aria-hidden="true" /><span><strong>{item.name} excluded:</strong> {item.reason}</span></div>)}
        <div className="arena-saved-row">
          <label className="arena-field" htmlFor="arena-saved-strategy"><span>Saved strategy slot</span><select id="arena-saved-strategy" value={savedId} onChange={(event) => selectSavedStrategy(event.target.value)}><option value="">No saved strategy</option>{savedStrategies.map((strategy) => <option key={strategy.strategy_id} value={strategy.strategy_id}>{strategy.name} · {strategy.source.topic}</option>)}</select></label>
          <div className="arena-saved-help">{savedStrategy ? <><Check size={14} aria-hidden="true" /> Loaded as a local <strong>USER_STRATEGY</strong> participant. The record does not imply a human profile or AI identity.</> : <><UserRound size={14} aria-hidden="true" />Create a compatible rule in Strategy Builder to add one saved participant.</>}</div>
          <Link className="btn btn-quiet arena-builder-link" to="/app/strategy-builder"><SlidersHorizontal size={15} aria-hidden="true" /> Adjust a strategy</Link>
        </div>
      </section>

      <section className="arena-panel" aria-labelledby="arena-rules-title">
        <div className="arena-panel-head"><div><p className="eyebrow">2 · Review rules</p><h2 id="arena-rules-title">Match contract</h2></div><span className="arena-panel-note">reproducible methodology</span></div>
        <div className="arena-rules-grid">
          <Rule label="Evidence" value="Nvidia Wikimedia daily pageviews" />
          <Rule label="Signal windows" value="7 complete UTC days → 7 complete UTC days" />
          <Rule label="Initial bankroll" value={formatCredits(ARENA_DEFAULT_RISK_POLICY.initial_credits)} />
          <Rule label="Stake policy" value={`${ARENA_DEFAULT_RISK_POLICY.stake_fraction * 100}% of balance · max ${ARENA_DEFAULT_RISK_POLICY.max_position_fraction * 100}% of start`} />
          <Rule label="Correct" value="Stake returned plus equal virtual reward" />
          <Rule label="Incorrect" value="Stake lost · no negative balance" />
          <Rule label="Missing / zero" value="Unavailable; no imputation or forced signal" />
          <Rule label="Ranking" value="Ending credits → accuracy → correct calls → stable ID" />
        </div>
        <div className="arena-rules-foot"><Database size={15} aria-hidden="true" /><span><strong>{NVIDIA_MOMENTUM_DATASET.dataset_id}</strong> · v{NVIDIA_MOMENTUM_DATASET.version} · {NVIDIA_MOMENTUM_DATASET.observation_start} → {NVIDIA_MOMENTUM_DATASET.observation_end}</span><code>{compactHash(NVIDIA_MOMENTUM_DATASET.content_sha256)}</code></div>
      </section>

      <section className="arena-run-panel" aria-labelledby="arena-run-title">
        <div><p className="eyebrow">3 · Run match</p><h2 id="arena-run-title">Freeze the evidence and compete</h2><p>{selectedParticipants.length} participant{selectedParticipants.length === 1 ? '' : 's'} selected · one deterministic historical replay.</p></div>
        <button type="button" className="btn btn-primary" onClick={runMatch} disabled={selectedParticipants.length < 2} aria-describedby="arena-run-help"><Play size={16} aria-hidden="true" /> Run historical match</button>
        <span id="arena-run-help" className="arena-run-help">No inference call, wallet, signer, market entry or transaction is made.</span>
      </section>
      {message && <p className="arena-message" role="alert">{message}</p>}

      {match && <ArenaResults match={match} inspectedResult={inspectedResult} onInspect={setInspectId} onRunAgain={runMatch} />}
    </div>
  )
}

function ParticipantChoice({ participant, selected, onToggle }: { participant: ArenaParticipant; selected: boolean; onToggle: () => void }) {
  const icon = participant.kind === 'BASELINE' ? <Trophy size={16} aria-hidden="true" /> : participant.kind === 'USER_STRATEGY' ? <UserRound size={16} aria-hidden="true" /> : <Bot size={16} aria-hidden="true" />
  return (
    <label className={`arena-participant${selected ? ' is-selected' : ''}`}>
      <input type="checkbox" checked={selected} onChange={onToggle} />
      <span className="arena-participant-icon">{icon}</span>
      <span className="arena-participant-main"><strong>{participant.name}</strong><small>{participant.kind === 'BASELINE' ? 'Benchmark' : participant.kind === 'USER_STRATEGY' ? 'Saved local strategy' : 'Deterministic bot'} · {participant.behavior.replace(/_/g, ' ')}</small><span>{participant.description}</span><code>strategy {compactHash(participant.strategy_hash)} · config {compactHash(participant.participant_config_hash)}</code></span>
      <span className="arena-check" aria-hidden="true"><Check size={14} /></span>
    </label>
  )
}

function Rule({ label, value }: { label: string; value: string }) {
  return <div className="arena-rule"><span>{label}</span><strong>{value}</strong></div>
}

function ArenaResults({ match, inspectedResult, onInspect, onRunAgain }: { match: ArenaMatch; inspectedResult: ArenaParticipantResult | null; onInspect: (id: string) => void; onRunAgain: () => void }) {
  return (
    <section className="arena-results" aria-labelledby="arena-results-title">
      <div className="arena-results-head"><div><p className="eyebrow">4 · Results</p><h2 id="arena-results-title">Historical leaderboard</h2><p>Virtual credits are a controlled score, not profit, token returns or a prediction of future performance.</p></div><button type="button" className="btn btn-quiet" onClick={onRunAgain}><RefreshCw size={15} aria-hidden="true" /> Run again</button></div>
      <div className="arena-summary-grid">
        <Summary label="Winner" value={match.leaderboard[0]?.participant_name ?? '—'} note={match.leaderboard[0] ? formatCredits(match.leaderboard[0].ending_credits) : 'No result'} />
        <Summary label="Shared eligible windows" value={String(match.shared_eligible_dates.length)} note={`${match.shared_benchmark_signal_dates.length} benchmark signal dates · ${match.shared_candidate_dates.length} candidates`} />
        <Summary label="Evidence cutoff" value={match.evidence_cutoff_utc.slice(0, 10)} note="UTC · no lookahead" />
        <Summary label="Result digest" value={compactHash(match.result_digest)} note={match.match_id} />
      </div>

      <div className="arena-leaderboard" aria-label="Arena leaderboard">
        {match.leaderboard.map((row) => <LeaderboardCard key={row.participant_id} row={row} selected={row.participant_id === inspectedResult?.participant_id} onInspect={() => onInspect(row.participant_id)} />)}
      </div>

      <div className="arena-inspector">
        <div className="arena-panel-head"><div><p className="eyebrow">5 · Inspect</p><h3>Decision ledger</h3></div><label className="arena-field arena-inspect-select" htmlFor="arena-inspect"><span>Participant</span><select id="arena-inspect" value={inspectedResult?.participant_id ?? ''} onChange={(event) => onInspect(event.target.value)}>{match.results.map((result) => <option key={result.participant_id} value={result.participant_id}>{result.participant_name}</option>)}</select></label></div>
        {inspectedResult ? <DecisionLedger result={inspectedResult} /> : <p className="arena-empty">No participant result is available.</p>}
      </div>

      <div className="arena-provenance">
        <div className="arena-panel-head"><div><p className="eyebrow">Evidence ledger</p><h3>Inspectability</h3></div><Database size={17} aria-hidden="true" /></div>
        <dl className="arena-provenance-grid"><div><dt>Match ID</dt><dd>{match.match_id}</dd></div><div><dt>Methodology</dt><dd>{match.methodology_version}</dd></div><div><dt>Dataset SHA-256</dt><dd>{match.dataset.content_sha256}</dd></div><div><dt>Source fixture SHA-256</dt><dd>{match.dataset.source_fixture_sha256}</dd></div><div><dt>Participant version</dt><dd>{match.participant_version}</dd></div><div><dt>Ranking</dt><dd>Ending credits, then accuracy, correct calls and stable participant ID.</dd></div></dl>
        <p className="arena-source"><ExternalLink size={14} aria-hidden="true" /> <a href={match.dataset.source_url} target="_blank" rel="noreferrer">Wikimedia Pageviews source contract</a> · {match.overlapping_windows.disclosure}</p>
        <p className="arena-safe"><ShieldCheck size={14} aria-hidden="true" /> Read-only boundary: wallet action, signing, transaction, market entry and AI inference are all false.</p>
      </div>
    </section>
  )
}

function Summary({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="arena-summary"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>
}

function LeaderboardCard({ row, selected, onInspect }: { row: ArenaMatch['leaderboard'][number]; selected: boolean; onInspect: () => void }) {
  return (
    <button type="button" className={`arena-leader-card${selected ? ' is-selected' : ''}`} onClick={onInspect} aria-pressed={selected}>
      <span className="arena-rank">#{row.rank}</span><span className="arena-leader-main"><strong>{row.participant_name}</strong><small>{row.participant_kind} · n={row.sample_size} settled · {row.signals_generated} signals</small></span><span className="arena-leader-value"><strong>{formatCredits(row.ending_credits)}</strong><small>{percent(row.accuracy)} accuracy</small></span><span className="arena-leader-stats"><span>{row.correct} correct</span><span>{row.incorrect} incorrect</span><span>{row.skipped} skipped</span><span>{row.unavailable} unavailable</span></span>
    </button>
  )
}

function DecisionLedger({ result }: { result: ArenaParticipantResult }) {
  return (
    <>
      <div className="arena-ledger-stats"><span><strong>{formatCredits(result.ending_credits)}</strong> ending</span><span>{percent(result.accuracy)} · n={result.sample_size}</span><span>drawdown {result.max_drawdown_credits == null ? '—' : `${formatCredits(result.max_drawdown_credits)} (${result.max_drawdown_percent?.toFixed(1)}%)`}</span><span>risk caps prevented {result.risk_limit_violations_prevented}</span></div>
      {!result.decision_records.length ? <div className="arena-empty"><strong>No decision records.</strong><p>{result.reason ?? 'The participant had no evaluable historical window.'}</p></div> : <div className="arena-decision-list">{result.decision_records.map((record) => <DecisionRecordRow key={record.decision_id} record={record} />)}</div>}
    </>
  )
}

function DecisionRecordRow({ record }: { record: ArenaDecisionRecord }) {
  const statusClass = `is-${record.status.toLowerCase()}`
  return <details className={`arena-decision ${statusClass}`}><summary><span><time dateTime={record.signal_date}>{record.signal_date}</time><strong>{record.status}</strong></span><span>{record.prediction ?? '—'} {record.outcome ? `→ ${record.outcome}` : ''}</span><span>{record.stake ? formatCredits(record.stake) : record.reason ?? 'No allocation'}</span></summary><div className="arena-decision-detail"><span>Cutoff</span><strong>{record.signal_cutoff_utc}</strong><span>Bankroll</span><strong>{formatCredits(record.bankroll_before)} → {formatCredits(record.bankroll_after)}</strong><span>Correct</span><strong>{record.correct == null ? '—' : record.correct ? 'Yes' : 'No'}</strong><span>Momentum</span><strong>{record.momentum_bps == null ? '—' : `${record.momentum_bps.toLocaleString('en-US')} bps`}</strong><span>Signal refs at cutoff</span><code>{record.signal_evidence_refs.length ? record.signal_evidence_refs.join(' · ') : 'none supplied'}</code><span>Outcome refs after cutoff</span><code>{record.outcome_evidence_refs.length ? record.outcome_evidence_refs.join(' · ') : 'none supplied'}</code></div></details>
}
