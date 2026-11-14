import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, CheckCircle2, CirclePause, CircleStop, Clock3, Database, ExternalLink, Info, Play, RefreshCw, ShieldAlert, ShieldCheck, Square, Zap } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Market, MarketDetail } from '../api/types'
import { useApi } from '../api/useApi'
import { NVIDIA_MOMENTUM_DATASET } from '../practice/fixtures/nvidia-momentum-v1'
import { builtInArenaParticipants } from '../arena/arena'
import {
  AUTOPILOT_DEFAULT_RISK,
  actionStatusLabel,
  approveManualReview,
  createPolicy,
  evaluateAutopilot,
  ledgerSnapshot,
  readAutopilotState,
  setPolicyStatus,
  strategyAutopilotCompatibility,
  validateAutopilotRisk,
  writeAutopilotState,
  type AutopilotAction,
  type AutopilotActionStatus,
  type AutopilotAgentContext,
  type AutopilotEvaluationResult,
  type AutopilotMode,
  type AutopilotRiskConfig,
} from '../autopilot/autopilot'
import { canonicalStrategyHash, evaluateStrategy, readStrategies, type StrategyDefinition } from '../strategy/strategy'
import './Autopilot.css'

interface AutopilotForm {
  risk: AutopilotRiskConfig
  mode: AutopilotMode
}

const emptyForm: AutopilotForm = { risk: { ...AUTOPILOT_DEFAULT_RISK }, mode: 'MANUAL_REVIEW' }
const formatCredits = (value: number) => `${value.toLocaleString('en-US')} credits`
const formatPercent = (value: number | null) => value == null ? '—' : `${value.toFixed(1)}%`
const compact = (value: string | null | undefined) => !value ? '—' : value.length > 26 ? `${value.slice(0, 17)}…${value.slice(-7)}` : value
const actionClass = (status: AutopilotActionStatus) => `is-${status.toLowerCase().replaceAll('_', '-')}`

export function Autopilot() {
  const [params, setParams] = useSearchParams()
  const [strategies, setStrategies] = useState<StrategyDefinition[]>(() => readStrategies())
  const [autopilotState, setAutopilotState] = useState(() => readAutopilotState())
  const [form, setForm] = useState<AutopilotForm>(emptyForm)
  const [runResult, setRunResult] = useState<AutopilotEvaluationResult | null>(null)
  const [message, setMessage] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [marketsState, reloadMarkets] = useApi(() => api.markets().then((response) => response.data), [])

  const builtInAgents = useMemo(() => builtInArenaParticipants().filter((participant) => participant.strategy), [])
  const requestedAgentId = params.get('agent')
  const requestedStrategyId = params.get('strategy')
  const requestedAgent = builtInAgents.find((participant) => participant.participant_id === requestedAgentId) ?? null
  const requestedStrategy = strategies.find((strategy) => strategy.strategy_id === requestedStrategyId) ?? null
  const defaultAgent = builtInAgents[0]
  const savedAgent = requestedStrategy ?? strategies[0] ?? null
  const selectedAgent: AutopilotAgentContext | null = requestedAgent
    ? { agent_id: requestedAgent.participant_id, agent_name: requestedAgent.name, agent_kind: requestedAgent.kind, agent_behavior: requestedAgent.behavior }
    : savedAgent
      ? { agent_id: `saved_${savedAgent.strategy_id}`, agent_name: `Saved: ${savedAgent.name}`, agent_kind: 'USER_STRATEGY', agent_behavior: 'SAVED_STRATEGY' }
      : defaultAgent
        ? { agent_id: defaultAgent.participant_id, agent_name: defaultAgent.name, agent_kind: defaultAgent.kind, agent_behavior: defaultAgent.behavior }
        : null
  const selected = requestedAgent?.strategy ?? savedAgent ?? defaultAgent?.strategy ?? null
  const selectionKey = requestedAgent ? `agent:${requestedAgent.participant_id}` : savedAgent ? `strategy:${savedAgent.strategy_id}` : defaultAgent ? `agent:${defaultAgent.participant_id}` : ''
  const evaluation = useMemo(() => selected ? evaluateStrategy(selected, NVIDIA_MOMENTUM_DATASET) : null, [selected])
  const compatibility = useMemo(() => selected ? strategyAutopilotCompatibility(selected, NVIDIA_MOMENTUM_DATASET) : null, [selected])
  const selectedPolicy = selected && autopilotState.policy?.strategy_id === selected.strategy_id && autopilotState.policy.strategy_hash === (selected ? canonicalStrategyHash(selected) : '') ? autopilotState.policy : null
  const ledger = selectedPolicy ? ledgerSnapshot(selectedPolicy, autopilotState.actions, runResult?.run_timestamp_utc ?? selectedPolicy.updated_at_utc) : null
  const recentActions = [...autopilotState.actions].reverse().slice(0, 12)

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'notch.strategy.builder.v1') setStrategies(readStrategies())
      if (event.key === 'notch.autopilot.v1') setAutopilotState(readAutopilotState())
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  useEffect(() => {
    if (!selected) return
    const existing = autopilotState.policy?.strategy_id === selected.strategy_id ? autopilotState.policy : null
    setForm(existing ? { risk: { ...existing.risk }, mode: existing.mode } : emptyForm)
  }, [selected, autopilotState.policy])

  function chooseStrategy(selection: string) {
    const next = new URLSearchParams(params)
    next.delete('agent')
    next.delete('strategy')
    if (selection.startsWith('agent:')) next.set('agent', selection.slice('agent:'.length))
    if (selection.startsWith('strategy:')) next.set('strategy', selection.slice('strategy:'.length))
    setParams(next, { replace: true })
    setRunResult(null)
    setMessage(null)
  }

  function updateRisk<K extends keyof AutopilotRiskConfig>(key: K, value: AutopilotRiskConfig[K]) {
    setForm((current) => ({ ...current, risk: { ...current.risk, [key]: value } }))
    setMessage(null)
  }

  function activate() {
    if (!selected) return
    if (!compatibility?.ok) {
      setMessage({ kind: 'error', text: compatibility?.reason ?? 'This strategy is not supported by the available genuine evidence.' })
      return
    }
    const errors = validateAutopilotRisk(form.risk)
    if (errors.length) {
      setMessage({ kind: 'error', text: errors.join(' ') })
      return
    }
    try {
      const existing = autopilotState.policy?.strategy_id === selected.strategy_id ? autopilotState.policy : null
      const policy = createPolicy(selected, form.risk, form.mode, new Date().toISOString(), existing, selectedAgent ?? undefined)
      const nextState = { ...autopilotState, policy }
      writeAutopilotState(nextState)
      setAutopilotState(nextState)
      setRunResult(null)
      setMessage({ kind: 'info', text: `Policy v${policy.version} is active in ${policy.mode === 'PAPER_AUTO' ? 'paper-auto' : 'manual-review'} mode. It has no wallet or market execution path.` })
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof Error ? error.message : 'Policy could not be activated.' })
    }
  }

  function changeStatus(status: 'ACTIVE' | 'PAUSED' | 'STOPPED') {
    const nextState = setPolicyStatus(autopilotState, status, new Date().toISOString())
    writeAutopilotState(nextState)
    setAutopilotState(nextState)
    setMessage({ kind: 'info', text: status === 'ACTIVE' ? 'Paper policy resumed.' : status === 'PAUSED' ? 'Paper policy paused; new evaluations will refuse actions.' : 'Paper policy stopped; activate a new revision before evaluating again.' })
  }

  async function evaluateNow() {
    if (!selected || !selectedPolicy) {
      setMessage({ kind: 'error', text: 'Activate the selected strategy revision before evaluating.' })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      if (marketsState.status === 'loading') {
        setMessage({ kind: 'info', text: 'Published market data is still loading. Try Evaluate Now again in a moment.' })
        return
      }
      if (marketsState.status === 'error') {
        const result = evaluateAutopilot(autopilotState, selected, NVIDIA_MOMENTUM_DATASET, [], { now: new Date().toISOString(), market_error: `Published market data is unavailable: ${marketsState.error.message}` })
        writeAutopilotState(result.state)
        setAutopilotState(result.state)
        setRunResult(result)
        return
      }
      const details = await Promise.all(marketsState.data.map(async (market) => {
        try { return (await api.market(market.market_id)).data as MarketDetail }
        catch { return market as Market }
      }))
      const result = evaluateAutopilot(autopilotState, selected, NVIDIA_MOMENTUM_DATASET, details, { now: new Date().toISOString() })
      writeAutopilotState(result.state)
      setAutopilotState(result.state)
      setRunResult(result)
      setMessage({ kind: 'info', text: result.eligible_market_count ? `${result.eligible_market_count} market passed compatibility checks; paper decisions were recorded locally.` : 'No eligible market was found. The policy recorded the blocking reasons without fabricating a target.' })
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof Error ? error.message : 'Evaluation failed without creating a paper action.' })
    } finally {
      setBusy(false)
    }
  }

  function approve(actionId: string) {
    const result = approveManualReview(autopilotState, actionId, new Date().toISOString())
    if (!result.action) return
    writeAutopilotState(result.state)
    setAutopilotState(result.state)
    setRunResult((current) => current ? { ...current, state: result.state, actions: [result.action!], ledger: selectedPolicy ? ledgerSnapshot(selectedPolicy, result.state.actions, new Date().toISOString()) : current.ledger } : current)
    setMessage({ kind: 'info', text: result.action.status === 'PAPER_ENTRY_APPROVED' ? 'Manual review approved one paper-only virtual position.' : result.action.explanation })
  }

  if (!selected || !selectedAgent) return <EmptyAutopilot />

  return (
    <div className="autopilot-page">
      <header className="page-head autopilot-head">
        <div>
          <Link className="autopilot-back" to="/app/arena"><ArrowLeft size={16} aria-hidden="true" /> Agent Arena</Link>
          <p className="eyebrow">PHASE 6B / AUTOPILOT V1</p>
          <h1>Paper Autopilot</h1>
          <p>Turn one validated Arena agent or saved strategy into a controlled, auditable paper policy. Evaluate Now runs only while this browser is open.</p>
        </div>
        <div className="autopilot-head-badge"><ShieldCheck size={15} aria-hidden="true" />Paper only · local device</div>
      </header>

      <section className="autopilot-boundary" aria-label="Autopilot boundary"><div><strong>No autonomous on-chain execution</strong><span>Virtual positions only · no wallet, signer, broadcast, market publication or paid inference.</span></div><p>V1 is a browser-local control surface. Closing the browser stops evaluation; there is no server scheduler or 24/7 claim.</p></section>

      <section className="autopilot-panel" aria-labelledby="autopilot-select-title">
        <div className="autopilot-panel-head"><div><p className="eyebrow">1 · Select and inspect</p><h2 id="autopilot-select-title">Validated strategy or Arena agent</h2></div><span className="autopilot-panel-note">notch.strategy/1</span></div>
        <div className="autopilot-selector-grid">
          <label className="autopilot-field" htmlFor="autopilot-strategy"><span>Agent / strategy revision</span><select id="autopilot-strategy" value={selectionKey} onChange={(event) => chooseStrategy(event.target.value)}><optgroup label="Deterministic Arena agents">{builtInAgents.map((participant) => <option key={participant.participant_id} value={`agent:${participant.participant_id}`}>{participant.name} · {participant.behavior.replace(/_/g, ' ')}</option>)}</optgroup><optgroup label="Saved strategies">{strategies.map((strategy) => <option key={strategy.strategy_id} value={`strategy:${strategy.strategy_id}`}>{strategy.name} · {strategy.source.topic}</option>)}</optgroup></select></label>
          {selected && <div className="autopilot-selected-rule"><span>{selectedAgent?.agent_name ?? 'Selected deterministic strategy'} · DETERMINISTIC STRATEGY</span><strong>{selected.source.topic} · {selected.signal_direction} · {selected.threshold_percent}% · {selected.observation_window.lookback_days}d → {selected.forecast_horizon_days}d</strong><code>{selected.strategy_id} · {canonicalStrategyHash(selected)}</code></div>}
        </div>
        {selected && <div className="autopilot-action-row">{selectedAgent?.agent_kind === 'USER_STRATEGY' ? <><Link className="btn btn-quiet" to={`/app/strategy-lab?strategy=${encodeURIComponent(selected.strategy_id)}`}>Inspect historical evaluation <ExternalLink size={14} aria-hidden="true" /></Link><Link className="btn btn-quiet" to={`/app/strategy-builder?strategy=${encodeURIComponent(selected.strategy_id)}`}>Adjust revision</Link></> : <Link className="btn btn-quiet" to="/app/arena">Open Arena record <ExternalLink size={14} aria-hidden="true" /></Link>}<span className="autopilot-safety-note"><Info size={14} aria-hidden="true" /> Deterministic definitions remain device-local and editable only when saved.</span></div>}
      </section>

      {selected && evaluation && <EvaluationSummary strategy={selected} evaluation={evaluation} compatibility={compatibility} />}

      <section className="autopilot-panel" aria-labelledby="autopilot-config-title">
        <div className="autopilot-panel-head"><div><p className="eyebrow">3 · Configure risk policy</p><h2 id="autopilot-config-title">Explicit limits before activation</h2></div><span className="autopilot-panel-note">enforced by domain logic</span></div>
        <div className="autopilot-form-grid">
          <label className="autopilot-field"><span>Virtual budget</span><input type="number" min="1" step="1" value={form.risk.budget_credits} onChange={(event) => updateRisk('budget_credits', Number(event.target.value))} /><small>Credits only; not NEAR or USDC.</small></label>
          <label className="autopilot-field"><span>Stake mode</span><select value={form.risk.stake_mode} onChange={(event) => updateRisk('stake_mode', event.target.value as AutopilotRiskConfig['stake_mode'])}><option value="PERCENTAGE">Allocation percentage</option><option value="FIXED">Fixed credits</option></select></label>
          <label className="autopilot-field"><span>{form.risk.stake_mode === 'PERCENTAGE' ? 'Allocation percentage' : 'Stake amount'}</span><input type="number" min="1" max={form.risk.stake_mode === 'PERCENTAGE' ? 100 : form.risk.budget_credits} step="1" value={form.risk.stake_value} onChange={(event) => updateRisk('stake_value', Number(event.target.value))} /><small>{form.risk.stake_mode === 'PERCENTAGE' ? `${Math.floor(form.risk.budget_credits * form.risk.stake_value / 100)} credits requested per action.` : 'Requested amount per action.'}</small></label>
          <label className="autopilot-field"><span>Maximum exposure</span><input type="number" min="1" step="1" value={form.risk.max_exposure_credits} onChange={(event) => updateRisk('max_exposure_credits', Number(event.target.value))} /><small>Total open paper stake.</small></label>
          <label className="autopilot-field"><span>Simultaneous positions</span><input type="number" min="1" step="1" value={form.risk.max_positions} onChange={(event) => updateRisk('max_positions', Number(event.target.value))} /><small>Open virtual positions at once.</small></label>
          <label className="autopilot-field"><span>Daily virtual-loss limit</span><input type="number" min="0" step="1" value={form.risk.daily_loss_limit_credits} onChange={(event) => updateRisk('daily_loss_limit_credits', Number(event.target.value))} /><small>Zero means no loss is permitted.</small></label>
          <label className="autopilot-field"><span>Decision cooldown</span><input type="number" min="0" step="1" value={form.risk.cooldown_seconds} onChange={(event) => updateRisk('cooldown_seconds', Number(event.target.value))} /><small>Seconds between processed decisions.</small></label>
          <label className="autopilot-field"><span>Execution mode</span><select value={form.mode} onChange={(event) => setForm((current) => ({ ...current, mode: event.target.value as AutopilotMode }))}><option value="MANUAL_REVIEW">Manual review</option><option value="PAPER_AUTO">Paper auto</option></select><small>{form.mode === 'MANUAL_REVIEW' ? 'Risk-passing actions wait for your review.' : 'Risk-passing actions create virtual positions automatically.'}</small></label>
        </div>
        <div className="autopilot-config-foot"><ShieldAlert size={15} aria-hidden="true" /><span>Activation stores the policy and audit records in <code>notch.autopilot.v1</code>. The browser owner can edit or delete this data; it is not server-verified.</span><button type="button" className="btn btn-primary" onClick={activate} disabled={!compatibility?.ok}><Zap size={15} aria-hidden="true" /> Activate paper policy</button></div>
      </section>

      <PolicyStatus policy={selectedPolicy} ledger={ledger} onStatus={changeStatus} />

      <section className="autopilot-run-panel" aria-labelledby="autopilot-run-title">
        <div><p className="eyebrow">5 · Evaluate</p><h2 id="autopilot-run-title">Observe → evaluate → check → decide</h2><p>Evaluate Now reads the current published-market API, then records every allowed or blocked outcome locally.</p></div>
        <div className="autopilot-api-state"><span className={`autopilot-dot is-${marketsState.status}`} aria-hidden="true" />{marketsState.status === 'loading' ? 'Loading published markets…' : marketsState.status === 'error' ? 'Published market API unavailable' : `${marketsState.data.length} published market${marketsState.data.length === 1 ? '' : 's'} returned`}<button type="button" className="icon-button" onClick={reloadMarkets} aria-label="Refresh published markets"><RefreshCw size={15} aria-hidden="true" /></button></div>
        <button type="button" className="btn btn-primary" onClick={evaluateNow} disabled={!selectedPolicy || busy}><Play size={16} aria-hidden="true" />{busy ? 'Evaluating…' : 'Evaluate Now'}</button>
        <span className="autopilot-run-help">Forward evaluation is manual and browser-bound. No background scheduler is installed.</span>
      </section>
      {message && <p className={`autopilot-message is-${message.kind}`} role={message.kind === 'error' ? 'alert' : 'status'}>{message.kind === 'error' ? <ShieldAlert size={15} aria-hidden="true" /> : <CheckCircle2 size={15} aria-hidden="true" />}{message.text}</p>}

      {runResult && <EvaluationResult result={runResult} onApprove={approve} />}

      <section className="autopilot-panel" aria-labelledby="autopilot-history-title">
        <div className="autopilot-panel-head"><div><p className="eyebrow">6 · Audit</p><h2 id="autopilot-history-title">Recent paper decisions</h2></div><span className="autopilot-panel-note">device-local ledger</span></div>
        {!recentActions.length ? <div className="autopilot-empty"><Clock3 size={22} aria-hidden="true" /><strong>No paper decisions yet.</strong><p>Activate a policy, then use Evaluate Now. A blocked evaluation is still recorded with its exact reason.</p></div> : <div className="autopilot-history">{recentActions.map((action) => <ActionRow key={action.action_id} action={action} onApprove={approve} />)}</div>}
      </section>

      <section className="autopilot-provenance" aria-labelledby="autopilot-provenance-title"><div className="autopilot-panel-head"><div><p className="eyebrow">Evidence and boundary</p><h2 id="autopilot-provenance-title">No fabricated eligibility</h2></div><Database size={17} aria-hidden="true" /></div><div className="autopilot-provenance-grid"><div><span>Supported evidence</span><strong>{NVIDIA_MOMENTUM_DATASET.dataset_id} · v{NVIDIA_MOMENTUM_DATASET.version}</strong><small>{NVIDIA_MOMENTUM_DATASET.observation_start} → {NVIDIA_MOMENTUM_DATASET.observation_end}</small></div><div><span>Dataset SHA-256</span><code>{NVIDIA_MOMENTUM_DATASET.content_sha256}</code></div><div><span>Source fixture SHA-256</span><code>{NVIDIA_MOMENTUM_DATASET.retrieval_provenance.source_fixture_sha256}</code></div><div><span>Forward freshness</span><strong>Frozen fixture only</strong><small>Stale observations block current forward paper entries.</small></div></div><p className="autopilot-safe"><ShieldCheck size={14} aria-hidden="true" /> Paper-only boundary: wallet action, signing, broadcast, market publication, contract interaction and NEAR AI inference are not called.</p></section>
    </div>
  )
}

function EmptyAutopilot() {
  return <div className="autopilot-page"><section className="autopilot-empty-page"><Zap size={30} aria-hidden="true" /><p className="eyebrow">PHASE 6B / AUTOPILOT V1</p><h1>Save a strategy before activating paper mode</h1><p>Autopilot only accepts validated <code>notch.strategy/1</code> definitions saved on this device.</p><Link className="btn btn-primary" to="/app/strategy-builder">Open Strategy Builder</Link></section></div>
}

function EvaluationSummary({ strategy, evaluation, compatibility }: { strategy: StrategyDefinition; evaluation: ReturnType<typeof evaluateStrategy>; compatibility: { ok: true } | { ok: false; reason: string } | null }) {
  return <section className="autopilot-evaluation" aria-labelledby="autopilot-evaluation-title"><div className="autopilot-panel-head"><div><p className="eyebrow">2 · Historical review</p><h2 id="autopilot-evaluation-title">Before paper activation</h2></div><span className={`autopilot-eval-status is-${evaluation.status.toLowerCase()}`}>{evaluation.status === 'EVALUATED' ? <CheckCircle2 size={14} aria-hidden="true" /> : <Info size={14} aria-hidden="true" />}{evaluation.status === 'EVALUATED' ? 'Genuine fixture evaluated' : evaluation.status === 'INSUFFICIENT_DATA' ? 'Insufficient data' : 'Unsupported evidence'}</span></div>{evaluation.status === 'EVALUATED' ? <><div className="autopilot-metrics"><Metric label="Accuracy" value={formatPercent(evaluation.accuracy)} note={`n=${evaluation.triggered_signals}`} /><Metric label="Correct / incorrect" value={`${evaluation.correct} / ${evaluation.incorrect}`} note="historical replay" /><Metric label="Eligible windows" value={`${evaluation.eligible_windows} / ${evaluation.candidate_windows}`} note="complete windows" /><Metric label="Skipped / unavailable" value={`${evaluation.skipped_windows} / ${evaluation.unavailable_windows}`} note="no forced signal" /></div><p className="autopilot-eval-note"><Info size={14} aria-hidden="true" /> {evaluation.overlap.disclosure} Historical accuracy does not authorize a forward action.</p></> : <div className="autopilot-unavailable"><strong>No supported historical evidence for this revision.</strong><p>{evaluation.reason}</p></div>}{!compatibility?.ok && <div className="autopilot-unavailable"><strong>Activation blocked for this strategy.</strong><p>{compatibility?.reason}</p></div>}<div className="autopilot-eval-foot"><span>Strategy revision {strategy.strategy_id} · {evaluation.strategy_hash}</span><Link to={`/app/strategy-lab?strategy=${encodeURIComponent(strategy.strategy_id)}`}>Open full evaluation lab <ExternalLink size={13} aria-hidden="true" /></Link></div></section>
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) { return <div className="autopilot-metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div> }

function PolicyStatus({ policy, ledger, onStatus }: { policy: ReturnType<typeof readAutopilotState>['policy']; ledger: ReturnType<typeof ledgerSnapshot> | null; onStatus: (status: 'ACTIVE' | 'PAUSED' | 'STOPPED') => void }) {
  return <section className="autopilot-status-panel" aria-labelledby="autopilot-status-title"><div className="autopilot-panel-head"><div><p className="eyebrow">4 · Policy state</p><h2 id="autopilot-status-title">{policy ? 'Paper policy control' : 'Not activated'}</h2></div>{policy && <span className={`autopilot-status-chip is-${policy.status.toLowerCase()}`}>{policy.status === 'ACTIVE' ? <CheckCircle2 size={14} aria-hidden="true" /> : policy.status === 'PAUSED' ? <CirclePause size={14} aria-hidden="true" /> : <CircleStop size={14} aria-hidden="true" />}{policy.status}</span>}</div>{!policy ? <p className="autopilot-status-copy">Set limits above and activate one saved strategy revision. No evaluation can create an action before activation.</p> : <><div className="autopilot-status-grid"><StatusValue label="Mode" value={policy.mode === 'PAPER_AUTO' ? 'Paper auto' : 'Manual review'} /><StatusValue label="Policy version" value={`v${policy.version}`} /><StatusValue label="Available budget" value={formatCredits(ledger?.available_budget ?? policy.risk.budget_credits)} /><StatusValue label="Current exposure" value={formatCredits(ledger?.current_exposure ?? 0)} /><StatusValue label="Open positions" value={`${ledger?.active_positions ?? 0} / ${policy.risk.max_positions}`} /><StatusValue label="Daily loss" value={`${formatCredits(ledger?.daily_loss ?? 0)} / ${formatCredits(policy.risk.daily_loss_limit_credits)}`} /></div><div className="autopilot-status-actions">{policy.status === 'ACTIVE' ? <button type="button" className="btn btn-quiet" onClick={() => onStatus('PAUSED')}><CirclePause size={15} aria-hidden="true" /> Pause</button> : policy.status === 'PAUSED' ? <button type="button" className="btn btn-quiet" onClick={() => onStatus('ACTIVE')}><Play size={15} aria-hidden="true" /> Resume</button> : <span className="autopilot-stopped-note"><Square size={13} aria-hidden="true" /> Stopped; activate a new policy revision to continue.</span>}{policy.status !== 'STOPPED' && <button type="button" className="btn btn-danger" onClick={() => onStatus('STOPPED')}><Square size={14} aria-hidden="true" /> Stop policy</button>}</div></>}</section>
}

function StatusValue({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div> }

function EvaluationResult({ result, onApprove }: { result: AutopilotEvaluationResult; onApprove: (actionId: string) => void }) {
  return <section className="autopilot-result" aria-labelledby="autopilot-result-title"><div className="autopilot-panel-head"><div><p className="eyebrow">Evaluation result</p><h2 id="autopilot-result-title">{result.eligible_market_count ? `${result.eligible_market_count} eligible market${result.eligible_market_count === 1 ? '' : 's'}` : 'No eligible market'}</h2></div><span className="autopilot-run-id">{result.run_id} · {result.run_timestamp_utc}</span></div>{result.no_eligible_market_reason && <div className="autopilot-no-market"><ShieldAlert size={17} aria-hidden="true" /><div><strong>No eligible market</strong><p>{result.no_eligible_market_reason}</p><small>Nothing was fabricated to create a paper match.</small></div></div>}{result.market_assessments.length > 0 && <div className="autopilot-assessments">{result.market_assessments.map((assessment) => <div className={`autopilot-assessment${assessment.eligible ? ' is-eligible' : ''}`} key={assessment.market_id}><div><strong>{assessment.market_id}</strong><span>{assessment.topic ?? 'topic not verified'} · rule {compact(assessment.rule_hash)}</span></div><b>{assessment.eligible ? 'Eligible' : 'Blocked'}</b>{!assessment.eligible && <p>{assessment.reasons.map((reason) => reason.explanation).join(' ')}</p>}</div>)}</div>}<div className="autopilot-result-actions">{result.actions.map((action) => <ActionRow key={action.action_id} action={action} onApprove={onApprove} />)}</div></section>
}

function ActionRow({ action, onApprove }: { action: AutopilotAction; onApprove: (actionId: string) => void }) {
  return <article className={`autopilot-action ${actionClass(action.status)}`}>
    <div className="autopilot-action-main"><span className="autopilot-action-status">{action.paper_result} · {actionStatusLabel(action.status)}</span><strong>{action.market_id ?? 'Policy-level evaluation'}</strong><small>{action.run_timestamp_utc} · {action.run_mode === 'FORWARD_EVALUATION' ? 'manual forward evaluation' : 'HISTORICAL REPLAY'}</small></div>
    <div className="autopilot-action-detail"><span><strong>{action.recommendation.agent_name}</strong> · {action.recommendation.direction} · {action.recommendation.eligibility_status}<br />{action.recommendation.reasoning}</span><code>Audit {action.audit_id} · {action.reason_code} · {action.idempotency_key}</code></div>
    <div className="autopilot-action-meta"><span>Freshness {action.recommendation.freshness_status}</span><span>Decision {action.recommendation.decision_timestamp_utc ?? '—'}</span><span>Evidence {compact(action.evidence_snapshot_id)}</span><span>Stake {formatCredits(action.stake || action.requested_stake)}</span><span>Exposure {formatCredits(action.exposure_before)} → {formatCredits(action.exposure_after)}</span>{action.simulated_position_id && <span>Position {compact(action.simulated_position_id)}</span>}</div>
    {action.status === 'NEEDS_MANUAL_REVIEW' && <button type="button" className="btn btn-primary autopilot-approve" onClick={() => onApprove(action.action_id)}>Approve paper entry</button>}
  </article>
}
