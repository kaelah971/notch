import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Check, FileJson, FlaskConical, RefreshCw, Save, Trash2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { NVIDIA_MOMENTUM_DATASET } from '../practice/fixtures/nvidia-momentum-v1'
import {
  STRATEGY_SOURCE_ID,
  SUPPORTED_TOPICS,
  SUPPORTED_WINDOW_DAYS,
  compileStrategy,
  createStrategyFromDraft,
  draftFromStrategy,
  draftToSentence,
  dryRunStrategy,
  emptyStrategyDraft,
  explainStrategy,
  parseStrategyIdea,
  readStrategies,
  removeStrategy,
  serializeStrategy,
  supportedTopic,
  updateStrategy,
  upsertStrategy,
  type MissingDataPolicy,
  type PredictedOutcome,
  type SignalDirection,
  type StrategyDefinition,
  type StrategyDraft,
  type StrategyField,
  type StrategyParseResult,
} from '../strategy/strategy'
import './StrategyBuilder.css'

const EXAMPLE_IDEA = 'If NVIDIA attention rises by at least 10% over the previous 7 days, predict UP for the next 7 days.'
function fieldValue(draft: StrategyDraft, field: StrategyField): string {
  const value = draft[field]
  return value == null ? '' : String(value)
}

function parseNumber(value: string): number | null {
  if (!value.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function statusLabel(result: StrategyParseResult | null, dirty: boolean) {
  if (dirty) return 'Manual draft'
  if (result?.status === 'PARSED') return 'Parsed rule'
  if (result?.status === 'UNSUPPORTED') return 'Unsupported request'
  if (result?.status === 'NEEDS_CONFIRMATION') return 'Needs confirmation'
  return 'Ready for input'
}

function draftToParseResult(draft: StrategyDraft): StrategyParseResult {
  const compiled = createStrategyFromDraft(draft)
  return compiled.ok ? {
    status: 'PARSED',
    message: 'Reopened a validated local strategy. Review the fields before saving changes.',
    normalized_input: draftToSentence(draft),
    draft,
    strategy: compiled.value,
    missing_fields: [],
    unsupported_reasons: [],
  } : {
    status: 'NEEDS_CONFIRMATION',
    message: 'This local draft still needs confirmation before saving changes.',
    normalized_input: draftToSentence(draft),
    draft,
    strategy: null,
    missing_fields: [],
    unsupported_reasons: compiled.errors,
  }
}

export function StrategyBuilder() {
  const [params] = useSearchParams()
  const candidateId = params.get('candidate')
  const [input, setInput] = useState(EXAMPLE_IDEA)
  const [parseResult, setParseResult] = useState<StrategyParseResult | null>(() => parseStrategyIdea(EXAMPLE_IDEA))
  const [draft, setDraft] = useState<StrategyDraft>(() => parseStrategyIdea(EXAMPLE_IDEA).draft)
  const [saved, setSaved] = useState<StrategyDefinition[]>(() => readStrategies())
  const [editing, setEditing] = useState<StrategyDefinition | null>(null)
  const [dirty, setDirty] = useState(false)
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null)
  const [candidateNote, setCandidateNote] = useState<string | null>(null)
  const [candidateLoading, setCandidateLoading] = useState(() => Boolean(candidateId))

  useEffect(() => {
    if (!candidateId) return
    let active = true
    api.scoutDetail(candidateId).then(
      (response) => {
        if (!active) return
        const candidate = response.data
        const trusted = candidate.source.id === STRATEGY_SOURCE_ID
          && candidate.candidate_status === 'REVIEWABLE'
          && candidate.freshness.status === 'FRESH'
          && candidate.is_notable
          && candidate.proposal != null
        if (!trusted) {
          setCandidateNote('This Scout record is not fresh and reviewable enough to prefill a strategy. Start from the editor instead.')
          return
        }
        if (!supportedTopic(candidate.topic)) {
          setCandidateNote('This Scout topic is outside the supported strategy schema. No topic was preselected.')
          return
        }
        const direction: SignalDirection = candidate.direction === 'FALLING' ? 'FALLING' : 'RISING'
        const outcome: PredictedOutcome = direction === 'RISING' ? 'UP' : 'DOWN'
        const threshold = candidate.proposal?.threshold_bps == null ? 20 : candidate.proposal.threshold_bps / 100
        const prefill: StrategyDraft = {
          ...emptyStrategyDraft(),
          name: `${candidate.topic} Scout strategy`,
          topic: candidate.topic,
          lookback_days: 7,
          signal_direction: direction,
          threshold_percent: threshold,
          forecast_horizon_days: 7,
          predicted_outcome: outcome,
          missing_data_policy: null,
        }
        const nextResult = parseStrategyIdea(draftToSentence(prefill))
        setInput(draftToSentence(prefill))
        setDraft({ ...nextResult.draft, name: prefill.name })
        setParseResult({ ...nextResult, message: `Prefilled from fresh ${candidate.topic} Wikimedia attention. Confirm the missing-data behavior before saving.` })
        setDirty(false)
        setCandidateNote(`Scout prefill uses only the verified ${candidate.source.article} source, direction, threshold and fresh observation window. It remains a research candidate, not a published market.`)
      },
      () => { if (active) setCandidateNote('The Scout candidate could not be loaded. No candidate fields were guessed.') },
    ).finally(() => { if (active) setCandidateLoading(false) })
    return () => { active = false }
  }, [candidateId])

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'notch.strategy.builder.v1') setSaved(readStrategies())
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  const previewValidation = useMemo(() => createStrategyFromDraft(draft, { id: editing?.strategy_id }), [draft, editing])
  const explanation = previewValidation.ok ? explainStrategy(previewValidation.value) : null
  const compiled = previewValidation.ok ? compileStrategy(previewValidation.value) : null
  const dryRun = previewValidation.ok ? dryRunStrategy(previewValidation.value, NVIDIA_MOMENTUM_DATASET) : null

  function parseIdea() {
    const next = parseStrategyIdea(input)
    setParseResult(next)
    setDraft(next.draft)
    setEditing(null)
    setDirty(false)
    setNotice(null)
  }

  function updateDraft<K extends keyof StrategyDraft>(field: K, value: StrategyDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }))
    setDirty(true)
    setNotice(null)
  }

  function saveStrategy() {
    const result = editing ? updateStrategy(editing, draft) : createStrategyFromDraft(draft)
    if (!result.ok) {
      setNotice({ text: result.errors.join(' '), error: true })
      return
    }
    if (!upsertStrategy(result.value)) {
      setNotice({ text: 'This browser did not allow local storage, so the strategy was not saved.', error: true })
      return
    }
    setSaved(readStrategies())
    const savedDraft = draftFromStrategy(result.value)
    const canonicalInput = draftToSentence(savedDraft)
    setEditing(result.value)
    setDraft(savedDraft)
    setInput(canonicalInput)
    setParseResult({ status: 'PARSED', message: 'Saved locally on this device. The validated rule is ready for a future historical evaluation.', normalized_input: canonicalInput, draft: savedDraft, strategy: result.value, missing_fields: [], unsupported_reasons: [] })
    setDirty(false)
    setNotice({ text: 'Saved locally on this device. It is ready for a future historical evaluation.' })
  }

  function reopen(strategy: StrategyDefinition) {
    setEditing(strategy)
    setDraft(draftFromStrategy(strategy))
    setInput(draftToSentence(draftFromStrategy(strategy)))
    setParseResult(draftToParseResult(draftFromStrategy(strategy)))
    setDirty(false)
    setNotice(null)
  }

  function startNew() {
    const next = emptyStrategyDraft()
    setEditing(null)
    setDraft(next)
    setInput('')
    setParseResult(null)
    setDirty(true)
    setNotice(null)
  }

  function deleteSaved(strategy: StrategyDefinition) {
    removeStrategy(strategy.strategy_id)
    setSaved(readStrategies())
    if (editing?.strategy_id === strategy.strategy_id) startNew()
    setNotice({ text: `Deleted “${strategy.name}” from this device.` })
  }

  return (
    <div className="strategy-builder">
      <header className="page-head strategy-head">
        <div>
          <Link className="strategy-back" to="/app/discover"><ArrowLeft size={16} aria-hidden="true" /> Discover</Link>
          <p className="eyebrow">RESEARCH SANDBOX / STRATEGY V1</p>
          <h1>Strategy Builder</h1>
          <p>Turn one supported attention idea into an explicit rule you can inspect, edit and save for future historical evaluation.</p>
        </div>
        <div className="strategy-local-badge"><span aria-hidden="true" />Device-local · no AI required</div>
      </header>

      {candidateLoading && <p className="strategy-status is-loading" role="status"><RefreshCw size={15} aria-hidden="true" /> Loading the verified Scout candidate…</p>}
      {candidateNote && <p className="strategy-candidate-note" role="note">{candidateNote}</p>}

      <div className="strategy-layout">
        <div className="strategy-main">
          <section className="strategy-panel strategy-language" aria-labelledby="strategy-language-title">
            <div className="strategy-panel-head"><div><p className="eyebrow">1 · Describe</p><h2 id="strategy-language-title">Your strategy idea</h2></div><span className="strategy-step">Plain English → rule</span></div>
            <label className="strategy-field strategy-field-wide" htmlFor="strategy-idea">
              <span>Supported attention statement</span>
              <textarea id="strategy-idea" value={input} onChange={(event) => setInput(event.target.value)} rows={3} aria-describedby="strategy-idea-help" placeholder={EXAMPLE_IDEA} />
            </label>
            <p id="strategy-idea-help" className="strategy-help">Constrained parser only: supported Wikimedia topics, complete UTC-day windows, percentage thresholds, UP/DOWN outcomes and explicit horizons. No model call is made.</p>
            <div className="strategy-action-row">
              <button type="button" className="btn btn-primary" onClick={parseIdea}>Parse idea</button>
              <button type="button" className="btn btn-quiet" onClick={() => { setInput(EXAMPLE_IDEA); setParseResult(parseStrategyIdea(EXAMPLE_IDEA)); setDraft(parseStrategyIdea(EXAMPLE_IDEA).draft); setEditing(null); setDirty(false); setNotice(null) }}>Use example</button>
            </div>
            {parseResult && (
              <div className={`strategy-parser-result is-${parseResult.status.toLowerCase()}`} role={parseResult.status === 'UNSUPPORTED' ? 'alert' : 'status'} aria-live="polite">
                <div className="strategy-result-title"><strong>{statusLabel(parseResult, dirty)}</strong><span>{parseResult.status === 'PARSED' && !dirty ? <Check size={14} aria-hidden="true" /> : null}</span></div>
                <p>{dirty ? 'The fields below have been edited manually. Re-parse the sentence to compare it with the structured rule.' : parseResult.message}</p>
                {!!parseResult.missing_fields.length && <p className="strategy-result-detail"><strong>Needs confirmation:</strong> {parseResult.missing_fields.join(', ')}</p>}
                {!!parseResult.unsupported_reasons.length && <p className="strategy-result-detail"><strong>Not supported:</strong> {parseResult.unsupported_reasons.join(' ')}</p>}
              </div>
            )}
          </section>

          <section className="strategy-panel" aria-labelledby="strategy-editor-title">
            <div className="strategy-panel-head"><div><p className="eyebrow">2 · Inspect and edit</p><h2 id="strategy-editor-title">Structured rule</h2></div><span className="strategy-step">All fields are explicit</span></div>
            <div className="strategy-form-grid">
              <label className="strategy-field strategy-field-wide" htmlFor="strategy-name"><span>Name</span><input id="strategy-name" value={draft.name} onChange={(event) => updateDraft('name', event.target.value)} placeholder="e.g. Nvidia attention momentum" /></label>
              <label className="strategy-field" htmlFor="strategy-topic"><span>Wikimedia topic</span><select id="strategy-topic" value={draft.topic ?? ''} onChange={(event) => updateDraft('topic', (event.target.value || null) as StrategyDraft['topic'])}><option value="">Choose a supported topic</option>{SUPPORTED_TOPICS.map((topic) => <option key={topic.value} value={topic.value}>{topic.value}</option>)}</select></label>
              <label className="strategy-field" htmlFor="strategy-window"><span>Observation window</span><select id="strategy-window" value={fieldValue(draft, 'lookback_days')} onChange={(event) => updateDraft('lookback_days', parseNumber(event.target.value))}><option value="">Choose days</option>{SUPPORTED_WINDOW_DAYS.map((days) => <option key={days} value={days}>{days} complete UTC days</option>)}</select></label>
              <label className="strategy-field" htmlFor="strategy-direction"><span>Attention direction</span><select id="strategy-direction" value={draft.signal_direction ?? ''} onChange={(event) => updateDraft('signal_direction', (event.target.value || null) as SignalDirection | null)}><option value="">Choose direction</option><option value="RISING">Rising</option><option value="FALLING">Falling</option></select></label>
              <label className="strategy-field" htmlFor="strategy-threshold"><span>Threshold (%)</span><input id="strategy-threshold" type="number" min="0.01" max="1000" step="0.01" value={fieldValue(draft, 'threshold_percent')} onChange={(event) => updateDraft('threshold_percent', parseNumber(event.target.value))} aria-describedby="strategy-threshold-help" /><small id="strategy-threshold-help">10% becomes 1,000 bps.</small></label>
              <label className="strategy-field" htmlFor="strategy-horizon"><span>Forecast horizon</span><select id="strategy-horizon" value={fieldValue(draft, 'forecast_horizon_days')} onChange={(event) => updateDraft('forecast_horizon_days', parseNumber(event.target.value))}><option value="">Choose days</option>{SUPPORTED_WINDOW_DAYS.map((days) => <option key={days} value={days}>{days} complete UTC days</option>)}</select></label>
              <label className="strategy-field" htmlFor="strategy-outcome"><span>Predicted outcome</span><select id="strategy-outcome" value={draft.predicted_outcome ?? ''} onChange={(event) => updateDraft('predicted_outcome', (event.target.value || null) as PredictedOutcome | null)}><option value="">Choose outcome</option><option value="UP">UP</option><option value="DOWN">DOWN</option></select></label>
              <label className="strategy-field" htmlFor="strategy-missing"><span>Missing-data behavior</span><select id="strategy-missing" value={draft.missing_data_policy ?? ''} onChange={(event) => updateDraft('missing_data_policy', (event.target.value || null) as MissingDataPolicy | null)}><option value="">Confirm behavior</option><option value="NO_SIGNAL">No signal; do not impute</option><option value="UNAVAILABLE">Mark unavailable; do not impute</option></select></label>
            </div>
            <div className="strategy-readonly"><span>Source methodology</span><strong>Wikimedia Pageviews · en.wikipedia.org · all-access · user</strong><code>{STRATEGY_SOURCE_ID}</code></div>
            {!previewValidation.ok && <div className="strategy-validation" role="alert"><strong>Cannot save yet.</strong><ul>{previewValidation.errors.map((error) => <li key={error}>{error}</li>)}</ul></div>}
            {notice && <p className={`strategy-notice${notice.error ? ' is-error' : ''}`} role={notice.error ? 'alert' : 'status'}>{notice.text}</p>}
            <div className="strategy-action-row"><button type="button" className="btn btn-primary" onClick={saveStrategy} disabled={!previewValidation.ok}><Save size={15} aria-hidden="true" />{editing ? 'Save changes' : 'Save strategy'}</button>{editing && <button type="button" className="btn btn-quiet" onClick={startNew}>New strategy</button>}</div>
            <details className="strategy-json" open={previewValidation.ok}>
              <summary><FileJson size={15} aria-hidden="true" /> Exact structured representation</summary>
              <pre>{previewValidation.ok ? serializeStrategy(previewValidation.value) : JSON.stringify(draft, null, 2)}</pre>
            </details>
          </section>

          {explanation && compiled && (
            <section className="strategy-panel" aria-labelledby="strategy-behavior-title">
              <div className="strategy-panel-head"><div><p className="eyebrow">3 · Verify behavior</p><h2 id="strategy-behavior-title">What this rule does</h2></div><span className="strategy-step">No lookahead</span></div>
              <p className="strategy-behavior-summary">{explanation.summary}</p>
              <div className="strategy-trigger"><span className="strategy-label">Example trigger</span><strong>{explanation.trigger}</strong></div>
              <ul className="strategy-evaluation-list">{explanation.evaluation.map((item) => <li key={item}>{item}</li>)}</ul>
              <details className="strategy-json"><summary><FlaskConical size={15} aria-hidden="true" /> Compiled evaluator handoff</summary><pre>{JSON.stringify(compiled, null, 2)}</pre></details>
              {dryRun?.available && <div className="strategy-dry-run"><div className="strategy-dry-head"><span><FlaskConical size={15} aria-hidden="true" /> Frozen Wikimedia example</span><strong>{dryRun.dataset_label}</strong></div><div className="strategy-dry-stats"><div><span>Signals</span><strong>{dryRun.signal_dates}</strong></div><div><span>Correct</span><strong>{dryRun.correct}</strong></div><div><span>Incorrect</span><strong>{dryRun.incorrect}</strong></div><div><span>Skipped</span><strong>{dryRun.no_signal_dates}</strong></div></div><p>Dry-run uses only the previous/current windows for the signal; the following horizon is read only to score the already-issued prediction. It is not a live forecast.</p></div>}
              {dryRun && !dryRun.available && previewValidation.ok && previewValidation.value.source.topic === 'Nvidia' && <p className="strategy-help">Frozen example unavailable: {dryRun.reason}</p>}
            </section>
          )}
        </div>

        <aside className="strategy-saved" aria-labelledby="saved-strategies-title">
          <section className="strategy-panel">
            <div className="strategy-panel-head"><div><p className="eyebrow">Local library</p><h2 id="saved-strategies-title">Saved strategies</h2></div><span className="strategy-local-label">this device only</span></div>
            <p className="strategy-help">Saved definitions stay in this browser. They are not synced, published, traded or sent to NEAR AI.</p>
            {!saved.length ? <div className="strategy-empty"><strong>No saved strategies yet.</strong><p>Complete the fields and save one to make it available for a future replay.</p></div> : <div className="strategy-saved-list">{saved.map((strategy) => <article className={`strategy-saved-card${editing?.strategy_id === strategy.strategy_id ? ' is-selected' : ''}`} key={strategy.strategy_id}><div><strong>{strategy.name}</strong><span>{strategy.source.topic} · {strategy.signal_direction} · {strategy.threshold_percent}% · {strategy.forecast_horizon_days}d</span><code>{strategy.strategy_id}</code></div><div className="strategy-saved-actions"><Link className="btn btn-quiet" to={`/app/strategy-lab?strategy=${encodeURIComponent(strategy.strategy_id)}`}>Evaluate</Link><button type="button" className="btn btn-quiet" onClick={() => reopen(strategy)}>Reopen</button><button type="button" className="strategy-icon-button" aria-label={`Delete ${strategy.name}`} onClick={() => deleteSaved(strategy)}><Trash2 size={15} aria-hidden="true" /></button></div></article>)}</div>}
          </section>
        </aside>
      </div>
    </div>
  )
}
