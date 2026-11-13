import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { formatUnits, relativeTo, USDC_DECIMALS } from '../api/format'
import { summarizeForecast, PREDICTION_STATUS_HELP, PREDICTION_STATUS_LABEL, predictionBadgeClass, type ForecastPassport } from '../api/predictions'
import type { Market, Position, PredictionStatus, PulseCoverage, PulseParticipant } from '../api/types'
import { useApi } from '../api/useApi'
import { ErrorState, SkeletonList } from '../components/States'
import { getFollowing, toggleFollow } from './follows'
import './Signals.css'

const MIN_COMPLETED = 3
const STATUS_ORDER: { status: PredictionStatus; key: keyof Pick<ForecastPassport, 'correct' | 'incorrect' | 'pending' | 'voided' | 'unknown'> }[] = [
  { status: 'CORRECT', key: 'correct' },
  { status: 'INCORRECT', key: 'incorrect' },
  { status: 'PENDING', key: 'pending' },
  { status: 'VOIDED', key: 'voided' },
  { status: 'UNKNOWN', key: 'unknown' },
]

type ProfileResult = { accountId: string; positions: Position[] | null; error: ApiError | null }

type ProfilesState = ReturnType<typeof useApi<ProfileResult[]>>

function useParticipantProfiles(participants: PulseParticipant[]): ProfilesState {
  const accounts = participants.map((item) => item.account_id).join('|')
  return useApi(async () => Promise.all(participants.map(async (participant): Promise<ProfileResult> => {
    try {
      const response = await api.positions(participant.account_id)
      return { accountId: participant.account_id, positions: response.data, error: null }
    } catch (error) {
      return {
        accountId: participant.account_id,
        positions: null,
        error: error instanceof ApiError ? error : new ApiError(0, 'UNKNOWN', String(error)),
      }
    }
  })), [accounts])
}

function verifiedPositions(positions: Position[], markets: Market[]): Position[] {
  const byId = new Map(markets.map((market) => [market.market_id, market]))
  return positions.filter((position) => {
    const market = byId.get(position.market_id)
    return Boolean(market && !market.is_historical_replay)
  })
}

function PassportBadges({ summary }: { summary: ForecastPassport }) {
  const visible = STATUS_ORDER.filter((item) => summary[item.key] > 0)
  return (
    <div className="discover-badges" aria-label="Forecast Passport result counts">
      {visible.length ? visible.map(({ status, key }) => (
        <span key={status} className={`badge ${predictionBadgeClass(status)}`} title={PREDICTION_STATUS_HELP[status]}>
          {status === 'UNKNOWN' ? 'Unknown' : PREDICTION_STATUS_LABEL[status]} {summary[key]}
        </span>
      )) : <span className="fine">No verified prediction results yet</span>}
    </div>
  )
}

function PassportSummary({ result, markets }: { result: ProfileResult | undefined; markets: Market[] }) {
  if (!result) return <span className="fine">Loading Forecast Passport…</span>
  if (result.error || !result.positions) return <span className="fine">Passport unavailable; receipt activity remains verified.</span>
  const summary = summarizeForecast(verifiedPositions(result.positions, markets))
  const accuracy = summary.accuracy == null ? 'Unavailable' : `${Number(summary.accuracy.toFixed(1))}%`
  return (
    <>
      <div className="discover-passport-stats">
        <span><strong>{accuracy}</strong><small>accuracy</small></span>
        <span><strong>{summary.completed}</strong><small>completed</small></span>
        <span><strong>{summary.total}</strong><small>markets</small></span>
      </div>
      <PassportBadges summary={summary} />
    </>
  )
}

function ParticipantCard({ participant, result, markets }: { participant: PulseParticipant; result?: ProfileResult; markets: Market[] }) {
  const [following, setFollowing] = useState(() => getFollowing().includes(participant.account_id))
  const volume = formatUnits(participant.confirmed_volume_base_units, USDC_DECIMALS)
  return (
    <article className="discover-card">
      <div className="discover-card-head">
        <div className="discover-account">
          <Link to={`/app/p/${encodeURIComponent(participant.account_id)}`} className="mono">{participant.account_id}</Link>
          <span>indexed {relativeTo(participant.last_activity_at_utc)}</span>
        </div>
        <button type="button" className={`btn ${following ? 'btn-quiet' : 'btn-primary'} discover-follow`} aria-pressed={following}
          onClick={() => setFollowing(toggleFollow(participant.account_id))}>
          {following ? 'Following' : 'Follow'}
        </button>
      </div>
      <p className="discover-receipt-meta">{participant.successful_entries} unique market{participant.successful_entries === 1 ? '' : 's'} · {participant.successful_entry_events} receipt{participant.successful_entry_events === 1 ? '' : 's'} · {volume} test-USDC</p>
      <div className="discover-passport">
        <div className="discover-passport-label">Forecast Passport</div>
        <PassportSummary result={result} markets={markets} />
      </div>
      <Link className="link discover-profile-link" to={`/app/p/${encodeURIComponent(participant.account_id)}`}>Inspect calls and make the same call →</Link>
    </article>
  )
}

export function ParticipantDirectory({ participants, markets, limit = 8 }: { participants: PulseParticipant[]; markets: Market[]; limit?: number }) {
  const [profiles] = useParticipantProfiles(participants.slice(0, limit))
  const results = profiles.status === 'ok' ? new Map(profiles.data.map((result) => [result.accountId, result])) : new Map<string, ProfileResult>()
  return (
    <section className="discover-section" aria-labelledby="discover-title">
      <div className="discover-section-head">
        <div><p className="eyebrow">Find the signal</p><h3 id="discover-title">Indexed forecasters</h3></div>
        <span className="discover-method">receipt activity, not a credibility rank</span>
      </div>
      <p className="discover-intro">Real accounts seen in the finalized Pulse window. Passport metrics come from their public market positions; follower counts and engagement are not available.</p>
      {!participants.length
        ? <div className="discover-empty"><strong>No indexed participants in this window.</strong><p>Pulse may be tracking a partial history, or no accepted calls have been observed here yet.</p></div>
        : profiles.status === 'loading'
          ? <SkeletonList n={2} h={108} />
          : <div className="discover-grid">{participants.slice(0, limit).map((participant) => <ParticipantCard key={participant.account_id} participant={participant} result={results.get(participant.account_id)} markets={markets} />)}</div>}
      {profiles.status === 'error' && <p className="fine">Some Forecast Passport profiles could not be read; open an account to retry.</p>}
    </section>
  )
}

function leaderboardSummary(result: ProfileResult, markets: Market[]): ForecastPassport | null {
  if (!result.positions) return null
  const rows = verifiedPositions(result.positions, markets)
  return rows.length ? summarizeForecast(rows) : null
}

export function PassportLeaderboard({ participants, markets, coverage }: { participants: PulseParticipant[]; markets: Market[]; coverage: PulseCoverage }) {
  const [profiles] = useParticipantProfiles(participants)
  const summaries = useMemo(() => {
    if (profiles.status !== 'ok') return []
    return profiles.data.map((result) => ({ result, summary: leaderboardSummary(result, markets) }))
      .filter((item): item is { result: ProfileResult; summary: ForecastPassport } => Boolean(item.summary))
      .sort((a, b) => (b.summary.accuracy ?? -1) - (a.summary.accuracy ?? -1) || b.summary.completed - a.summary.completed || a.result.accountId.localeCompare(b.result.accountId))
  }, [profiles, markets])
  const ranked = summaries.filter((item) => item.summary.completed >= MIN_COMPLETED)
  const profileReadFailures = profiles.status === 'ok' ? profiles.data.filter((result) => result.error || !result.positions).length : 0

  return (
    <section className="leaderboard-section" aria-labelledby="leaderboard-title">
      <div className="discover-section-head">
        <div><p className="eyebrow">Verified sample</p><h2 id="leaderboard-title">Forecast leaderboard</h2></div>
        <span className="discover-method">minimum n={MIN_COMPLETED}</span>
      </div>
      <p className="discover-intro">Ranked by finalized market-level accuracy: Correct ÷ (Correct + Incorrect). Pending, Voided, Unknown, historical demonstrations and repeated entries in one market do not improve a rank.</p>
      {!coverage.available && <div className="discover-empty"><strong>Leaderboard unavailable.</strong><p>{coverage.scope} Coverage is {coverage.status}; no complete ranking is claimed.</p></div>}
      {coverage.available && profiles.status === 'loading' && <SkeletonList n={3} h={72} />}
      {coverage.available && profiles.status === 'error' && <ErrorState error={new ApiError(0, 'PROFILE_READ_FAILED', 'Public Passport profiles could not be read.')} onRetry={() => window.location.reload()} />}
      {coverage.available && profiles.status === 'ok' && !ranked.length && (
        <div className="discover-empty">
          <strong>{!participants.length ? 'No indexed participants yet.' : profileReadFailures === participants.length ? 'Passport profiles unavailable.' : 'No ranked forecasters yet.'}</strong>
          <p>{!participants.length ? 'The selected finalized coverage window contains no receipt-backed participants.' : profileReadFailures === participants.length ? 'Public Passport reads failed, so no ranking is claimed.' : `Ranking requires at least ${MIN_COMPLETED} finalized Correct/Incorrect market predictions. The current indexed sample has not met that threshold.`}</p>
        </div>
      )}
      {coverage.available && ranked.length > 0 && (
        <ol className="leaderboard-list">
          {ranked.map(({ result, summary }, index) => (
            <li key={result.accountId} className="leaderboard-row">
              <span className="leaderboard-rank mono">{index + 1}</span>
              <div className="leaderboard-account"><Link to={`/app/p/${encodeURIComponent(result.accountId)}`} className="mono">{result.accountId}</Link><PassportBadges summary={summary} /></div>
              <span className="leaderboard-score"><strong>{Number((summary.accuracy ?? 0).toFixed(1))}%</strong><small>n={summary.completed}</small></span>
            </li>
          ))}
        </ol>
      )}
      <p className="fine">Coverage: {coverage.status} · {coverage.scope}. This view does not show follower counts or transaction-count ranks.</p>
    </section>
  )
}
