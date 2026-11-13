import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, CheckCircle2, ChevronDown, Database, ExternalLink, FileSearch, FlaskConical, Info, ShieldCheck } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { NVIDIA_MOMENTUM_DATASET } from '../practice/fixtures/nvidia-momentum-v1'
import {
  compareStrategies,
  evaluateStrategy,
  readStrategies,
  type StrategyComparison,
  type StrategyDefinition,
  type StrategyEvaluation,
  type StrategyEvaluationDecision,
} from '../strategy/strategy'
import './StrategyLab.css'

function percent(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function percentagePoints(value: number | null): string {
  if (value == null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)} pp`
}

function integer(value: number): string { return value.toLocaleString('en-US') }

function statusText(status: StrategyEvaluation['status']): string {
  return status === 'EVALUATED' ? 'Evaluated' : status === 'INSUFFICIENT_DATA' ? 'Insufficient data' : 'Unsupported dataset'
}

function strategySummary(strategy: StrategyDefinition): string {
  return `${strategy.source.topic} · ${strategy.signal_direction} · ${strategy.threshold_percent}% · ${strategy.observation_window.lookback_days}d → ${strategy.forecast_horizon_days}d`
}

export function StrategyLab() {
  const [params, setParams] = useSearchParams()
  const [strategies, setStrategies] = useState<StrategyDefinition[]>(() => readStrategies())
  const requestedId = params.get('strategy')
  const selected = strategies.find((strategy) => strategy.strategy_id === requestedId) ?? strategies[0] ?? null
  const selectedId = selected?.strategy_id ?? ''
  const compareId = params.get('compare') ?? ''
  const comparisonStrategy = strategies.find((strategy) => strategy.strategy_id === compareId) ?? null
  const evaluation = useMemo(() => selected ? evaluateStrategy(selected, NVIDIA_MOMENTUM_DATASET) : null, [selected])
  const comparison = useMemo(() => selected && comparisonStrategy ? compareStrategies(selected, comparisonStrategy, NVIDIA_MOMENTUM_DATASET) : null, [selected, comparisonStrategy])

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'notch.strategy.builder.v1') setStrategies(readStrategies())
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  function chooseStrategy(strategyId: string) {
    const next = new URLSearchParams(params)
    if (strategyId) next.set('strategy', strategyId)
    else next.delete('strategy')
    next.delete('compare')
    setParams(next, { replace: true })
  }

  function chooseComparison(strategyId: string) {
    const next = new URLSearchParams(params)
    if (strategyId) next.set('compare', strategyId)
    else next.delete('compare')
    setParams(next, { replace: true })
  }

  return (
    <div className="strategy-lab">
      <header className="page-head strategy-lab-head">
        <div>
          <Link className="strategy-back" to="/app/strategy-builder"><ArrowLeft size={16} aria-hidden="true" /> Strategy Builder</Link>
          <p className="eyebrow">RESEARCH SANDBOX / EVALUATION LAB V1</p>
          <h1>Strategy Evaluation Lab</h1>
          <p>Replay saved rules against genuine, frozen Wikimedia observations. Results are hypothetical historical evidence, not trading performance.</p>
        </div>
        <div className="strategy-lab-badge"><ShieldCheck size={15} aria-hidden="true" />Historical only · no wallet</div>
      </header>

      {!strategies.length ? (
        <section className="lab-empty" aria-labelledby="lab-empty-title">
          <FlaskConical size={26} aria-hidden="true" />
          <h2 id="lab-empty-title">Save a strategy before evaluating it</h2>
          <p>The lab only evaluates validated <code>notch.strategy/1</code> definitions saved on this device.</p>
          <Link className="btn btn-primary" to="/app/strategy-builder">Open Strategy Builder</Link>
        </section>
      ) : (
        <>
          <section className="lab-panel lab-selector" aria-labelledby="lab-selector-title">
            <div className="lab-panel-head"><div><p className="eyebrow">1 · Select</p><h2 id="lab-selector-title">Saved strategy</h2></div><span className="lab-panel-note">device-local definitions</span></div>
            <div className="lab-selector-grid">
              <label className="lab-field" htmlFor="lab-strategy"><span>Strategy to evaluate</span><select id="lab-strategy" value={selectedId} onChange={(event) => chooseStrategy(event.target.value)}>{strategies.map((strategy) => <option key={strategy.strategy_id} value={strategy.strategy_id}>{strategy.name} · {strategy.source.topic}</option>)}</select></label>
              {selected && <div className="lab-selected-rule"><span className="lab-label">Compiled rule</span><strong>{strategySummary(selected)}</strong><code>{selected.strategy_id}</code></div>}
            </div>
            {selected && <div className="lab-action-row"><Link className="btn btn-quiet" to="/app/strategy-builder">Edit in Builder</Link><span className="lab-safety-note"><Info size={14} aria-hidden="true" /> No market, wallet, contract, or AI action is available here.</span></div>}
          </section>

          {selected && evaluation && <EvaluationPanel strategy={selected} evaluation={evaluation} />}

          {selected && (
            <section className="lab-panel lab-compare" aria-labelledby="lab-compare-title">
              <div className="lab-panel-head"><div><p className="eyebrow">3 · Compare</p><h2 id="lab-compare-title">Baseline or another saved rule</h2></div><span className="lab-panel-note">matched windows disclosed</span></div>
              <label className="lab-field lab-compare-select" htmlFor="lab-compare"><span>Compare with another strategy</span><select id="lab-compare" value={compareId} onChange={(event) => chooseComparison(event.target.value)}><option value="">Choose a saved strategy</option>{strategies.filter((strategy) => strategy.strategy_id !== selected.strategy_id).map((strategy) => <option key={strategy.strategy_id} value={strategy.strategy_id}>{strategy.name} · {strategy.source.topic}</option>)}</select></label>
              {!comparisonStrategy && <p className="lab-help">Always-UP is shown in the evaluation summary. Add another saved rule here to see matched-window coverage and signal-population differences.</p>}
              {comparison && comparisonStrategy && <ComparisonPanel comparison={comparison} first={selected} second={comparisonStrategy} />}
            </section>
          )}
        </>
      )}
    </div>
  )
}

function EvaluationPanel({ strategy, evaluation }: { strategy: StrategyDefinition; evaluation: StrategyEvaluation }) {
  const hasResults = evaluation.status === 'EVALUATED'
  const sampleWarning = hasResults && evaluation.triggered_signals < 10
  return (
    <>
      <section className="lab-panel lab-summary" aria-labelledby="lab-summary-title">
        <div className="lab-panel-head"><div><p className="eyebrow">2 · Evaluate</p><h2 id="lab-summary-title">Historical evaluation</h2></div><span className={`lab-status lab-status-${evaluation.status.toLowerCase()}`}>{evaluation.status === 'EVALUATED' ? <CheckCircle2 size={14} aria-hidden="true" /> : <Info size={14} aria-hidden="true" />}{statusText(evaluation.status)}</span></div>
        {evaluation.status !== 'EVALUATED' ? <div className="lab-unavailable" role="status"><strong>{evaluation.status === 'UNSUPPORTED' ? 'This saved rule is not supported by the available genuine fixture.' : 'The available fixture is too short for this rule.'}</strong><p>{evaluation.reason}</p><p>No observations were invented and no accuracy claim was produced.</p></div> : <>
          <div className="lab-metric-grid">
            <Metric label="Eligible windows" value={`${integer(evaluation.eligible_windows)} / ${integer(evaluation.candidate_windows)}`} note="complete and evaluable" />
            <Metric label="Triggered signals" value={integer(evaluation.triggered_signals)} note="sample size n" />
            <Metric label="Accuracy" value={percent(evaluation.accuracy)} note={`n=${integer(evaluation.triggered_signals)}`} />
            <Metric label="Correct / incorrect" value={`${integer(evaluation.correct)} / ${integer(evaluation.incorrect)}`} note="hypothetical outcomes" />
            <Metric label="Skipped windows" value={integer(evaluation.skipped_windows)} note="below threshold" />
            <Metric label="Unavailable windows" value={integer(evaluation.unavailable_windows)} note="missing or zero baseline" />
          </div>
          <div className="lab-baseline"><div><span className="lab-label">Defined baseline</span><strong>Always UP on the same triggered signal dates</strong></div><div className="lab-baseline-stats"><span>{percent(evaluation.baseline.accuracy)} <small>accuracy</small></span><span>n={integer(evaluation.baseline.evaluated_signals)}</span><span>{percentagePoints(evaluation.baseline.percentage_point_difference)} <small>strategy − baseline</small></span></div></div>
          {sampleWarning && <div className={`lab-warning${evaluation.triggered_signals === 0 ? ' is-strong' : ''}`} role="note"><Info size={15} aria-hidden="true" /><span>{evaluation.triggered_signals === 0 ? 'No triggered signals were available, so accuracy is undefined.' : `Small sample: only ${evaluation.triggered_signals} triggered signal${evaluation.triggered_signals === 1 ? '' : 's'} are scored. This is not evidence of general performance.`}</span></div>}
          <div className="lab-disclosure"><Info size={15} aria-hidden="true" /><span>{evaluation.overlap.disclosure} Results are not simulated profit, token returns, positions, or on-chain predictions.</span></div>
        </>}
      </section>

      {hasResults && <>
        <ProvenancePanel strategy={strategy} evaluation={evaluation} />
        <DecisionPanel evaluation={evaluation} />
      </>}
    </>
  )
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="lab-metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>
}

function ProvenancePanel({ strategy, evaluation }: { strategy: StrategyDefinition; evaluation: StrategyEvaluation }) {
  return (
    <section className="lab-panel lab-provenance" aria-labelledby="lab-provenance-title">
      <div className="lab-panel-head"><div><p className="eyebrow">Evidence ledger</p><h2 id="lab-provenance-title">Reproducibility and provenance</h2></div><Database size={18} aria-hidden="true" /></div>
      <dl className="lab-provenance-grid">
        <div><dt>Strategy schema</dt><dd>{evaluation.schema_version}</dd></div>
        <div><dt>Strategy identity</dt><dd>{strategy.strategy_id}</dd></div>
        <div><dt>Strategy revision hash</dt><dd>{evaluation.strategy_hash}</dd></div>
        <div><dt>Evaluation methodology</dt><dd>{evaluation.evaluation_methodology_version}</dd></div>
        <div><dt>Dataset</dt><dd>{evaluation.dataset_label} · v{evaluation.dataset_version}</dd></div>
        <div><dt>Dataset dates</dt><dd>{evaluation.dataset_start_utc} → {evaluation.dataset_end_utc}</dd></div>
        <div><dt>Evaluated signal dates</dt><dd>{evaluation.evaluated_start_utc} → {evaluation.evaluated_end_utc}</dd></div>
        <div><dt>Dataset SHA-256</dt><dd><code>{evaluation.dataset_content_sha256}</code></dd></div>
        <div><dt>Result digest</dt><dd><code>{evaluation.result_digest}</code></dd></div>
      </dl>
      <p className="lab-source"><FileSearch size={14} aria-hidden="true" /> Source: <a href={evaluation.source_url ?? '#'} target="_blank" rel="noreferrer">Wikimedia Pageviews fixture <ExternalLink size={12} aria-hidden="true" /></a></p>
      <details className="lab-json"><summary><ChevronDown size={15} aria-hidden="true" /> Show compiled evaluation contract</summary><pre>{JSON.stringify({ strategy: strategy, evaluation: evaluation }, null, 2)}</pre></details>
    </section>
  )
}

function DecisionPanel({ evaluation }: { evaluation: StrategyEvaluation }) {
  return (
    <section className="lab-panel lab-decisions" aria-labelledby="lab-decisions-title">
      <div className="lab-panel-head"><div><p className="eyebrow">4 · Inspect</p><h2 id="lab-decisions-title">Historical decisions</h2></div><span className="lab-panel-note">{integer(evaluation.decisions.length)} triggered rows</span></div>
      {!evaluation.decisions.length ? <div className="lab-empty-inline"><strong>No historical signal cleared the rule.</strong><p>The complete windows were evaluated, but none reached the saved threshold.</p></div> : <div className="lab-table-scroll"><table className="lab-decision-table"><caption>Each row is a hypothetical signal generated at the decision cutoff.</caption><thead><tr><th scope="col">Decision cutoff</th><th scope="col">Momentum</th><th scope="col">Rule</th><th scope="col">Prediction</th><th scope="col">Observed outcome</th><th scope="col">Result</th><th scope="col">Evidence</th></tr></thead><tbody>{evaluation.decisions.map((decision) => <DecisionRow key={decision.signal_date} decision={decision} />)}</tbody></table></div>}
      {!!evaluation.unavailable.length && <details className="lab-unavailable-list"><summary>Unavailable window details · {integer(evaluation.unavailable.length)}</summary><ul>{evaluation.unavailable.map((item) => <li key={item.signal_date}><strong>{item.signal_date}</strong> · {item.reason === 'ZERO_BASELINE' ? 'previous window had zero views' : `missing ${item.missing_dates.join(', ')}`} · policy: {item.policy_action === 'SKIP_NO_SIGNAL' ? 'skip signal' : 'unavailable'}</li>)}</ul></details>}
    </section>
  )
}

function DecisionRow({ decision }: { decision: StrategyEvaluationDecision }) {
  return <tr><td><strong>{decision.signal_date}</strong><small>cutoff 23:59 UTC</small></td><td>{decision.momentum_bps >= 0 ? '+' : ''}{integer(decision.momentum_bps)} bps</td><td>≥ {integer(decision.threshold_bps)} bps</td><td><span className="lab-outcome">{decision.prediction}</span></td><td><span className="lab-outcome">{decision.outcome}</span></td><td><span className={`lab-result ${decision.correct ? 'is-correct' : 'is-incorrect'}`}>{decision.correct ? 'Correct' : 'Incorrect'}</span></td><td><details className="lab-evidence"><summary>View windows</summary><div><span>Previous</span><strong>{decision.previous_window.start} → {decision.previous_window.end} · {integer(decision.previous_window.sum_views)} views</strong><span>Signal</span><strong>{decision.signal_window.start} → {decision.signal_window.end} · {integer(decision.signal_window.sum_views)} views</strong><span>Target</span><strong>{decision.target_window.start} → {decision.target_window.end} · {integer(decision.target_window.sum_views)} views</strong></div></details></td></tr>
}

function ComparisonPanel({ comparison, first, second }: { comparison: StrategyComparison; first: StrategyDefinition; second: StrategyDefinition }) {
  if (!comparison.available) return <div className="lab-unavailable" role="status"><strong>Comparison unavailable.</strong><p>{comparison.reason}</p></div>
  const rows = [
    ['Eligible windows (full)', `${comparison.first.eligible_windows}`, `${comparison.second.eligible_windows}`],
    ['Triggered signals (full)', `${comparison.first.triggered_signals}`, `${comparison.second.triggered_signals}`],
    ['Matched-window signals', `${comparison.matched.first.triggered_signals}`, `${comparison.matched.second.triggered_signals}`],
    ['Matched-window accuracy', `${percent(comparison.matched.first.accuracy)} (n=${comparison.matched.first.triggered_signals})`, `${percent(comparison.matched.second.accuracy)} (n=${comparison.matched.second.triggered_signals})`],
    ['Matched Always-UP baseline', `${percent(comparison.matched.first.baseline_accuracy)} (${percentagePoints(comparison.matched.first.percentage_point_difference)})`, `${percent(comparison.matched.second.baseline_accuracy)} (${percentagePoints(comparison.matched.second.percentage_point_difference)})`],
  ]
  return <div className="lab-comparison-result"><div className="lab-match-strip"><span><strong>{integer(comparison.matched_eligible_windows)}</strong> matched eligible windows</span><span><strong>{integer(comparison.matched_signal_windows)}</strong> matched triggered dates</span></div><div className="lab-compare-table"><div className="lab-compare-row lab-compare-header"><span>Metric</span><strong>{first.name}</strong><strong>{second.name}</strong></div>{rows.map(([label, a, b]) => <div className="lab-compare-row" key={label}><span>{label}</span><strong>{a}</strong><strong>{b}</strong></div>)}</div><div className="lab-compare-warnings">{comparison.warnings.map((warning) => <p key={warning}><Info size={14} aria-hidden="true" />{warning}</p>)}</div></div>
}
