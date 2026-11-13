import { useState } from 'react'
import { Share2 } from 'lucide-react'
import type { Market, PredictionStatus } from '../api/types'
import { formatUtc } from '../api/format'
import { isOpenForEntry, marketTitle } from '../components/market'
import { ShareSheet, marketUrl } from './ShareSheet'

const statusText = (m: Market) =>
  isOpenForEntry(m) ? 'Open prediction' : m.is_historical_replay ? 'Resolved demonstration' : m.winning_choice ? `Resolved: ${m.winning_choice}` : 'Closed'

/** Share any market — no position needed. */
export function ShareMarketButton({ m, compact = false }: { m: Market; compact?: boolean }) {
  const [open, setOpen] = useState(false)
  const title = marketTitle(m)
  return (
    <>
      <button type="button" className={compact ? 'share-icon' : 'btn btn-quiet'} aria-label={`Share: ${title}`}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(true) }}>
        <Share2 size={compact ? 16 : 16} />{!compact && ' Share'}
      </button>
      {open && (
        <ShareSheet onClose={() => setOpen(false)}
          text={isOpenForEntry(m) ? `${title} Make your call on Notch.` : `${title} — see the evidence on Notch.`}
          spec={{
            kind: 'market', title, choices: m.choices, status: statusText(m), url: marketUrl(m.market_id),
            deadline: isOpenForEntry(m) ? `Entries close ${formatUtc(m.close_at_utc)}` : `Closed ${formatUtc(m.close_at_utc)}`,
          }} />
      )}
    </>
  )
}

/**
 * Share a confirmed call. Callers must only render this after the market contract has
 * confirmed the position (EntryPanel's confirmed state, or a Portfolio position read).
 */
export function ShareCallButton({ m, choice, stake, confirmedAt, txRef, account, result, className = 'btn btn-primary' }: {
  m: Market
  choice: string
  stake: string
  confirmedAt: string | null
  txRef: string | null
  account: string
  result?: { status: PredictionStatus; outcome: string | null; evidenceHash?: string | null; marketId?: string }
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [showAccount, setShowAccount] = useState(false)
  const title = marketTitle(m)
  const normalizedTxRef = txRef?.trim() || null
  const finalized = result && result.status !== 'PENDING'
  const resultText = result?.status === 'CORRECT' || result?.status === 'INCORRECT'
    ? ` Final outcome: ${result.outcome ?? 'unavailable'}. Notch verified the result from the market contract.`
    : result?.status === 'VOIDED'
      ? ' The market was voided or refunded; it is excluded from accuracy.'
      : result?.status === 'UNKNOWN'
        ? ' The result is unavailable because the finalized state or original call could not be verified.'
        : ''
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}><Share2 size={16} /> {finalized ? 'Share result' : 'Share my call'}</button>
      {open && (
        <ShareSheet onClose={() => setOpen(false)} allowAccount={showAccount} onToggleAccount={setShowAccount}
          text={finalized ? `I called ${choice} on “${title}”.${resultText}` : `I called ${choice} on “${title}” — think I’m wrong? Make your call on Notch.`}
          spec={{
            kind: 'call', title, choice, stake, confirmedAt, txRef: normalizedTxRef,
            verification: normalizedTxRef ? 'tx' : 'contract-read', result,
            account: showAccount ? account : null,
            url: marketUrl(m.market_id),
          }} />
      )}
    </>
  )
}

/** Share a local-only practice call without implying wallet or transaction verification. */
export function SharePracticeButton({ m, choice, stake, result, className = 'btn btn-quiet' }: {
  m: Market
  choice: string
  stake: string
  result?: { status: PredictionStatus; outcome: string | null; evidenceHash?: string | null; marketId?: string }
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const title = marketTitle(m)
  const finalized = result && result.status !== 'PENDING'
  const resultText = result?.status === 'CORRECT' || result?.status === 'INCORRECT'
    ? ` Final outcome: ${result.outcome ?? 'unavailable'} from the published market state.`
    : result?.status === 'VOIDED'
      ? ' The published market was voided; practice credits are refunded by the local score.'
      : result?.status === 'UNKNOWN'
        ? ' The published result could not be verified from available evidence.'
        : ''
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}><Share2 size={16} /> {finalized ? 'Share practice result' : 'Share practice call'}</button>
      {open && (
        <ShareSheet onClose={() => setOpen(false)}
          text={finalized ? `I practised ${choice} on “${title}”.${resultText} Practice credits only.` : `I practised ${choice} on “${title}” with ${stake} practice credits. No wallet required.`}
          spec={{
            kind: 'call', title, choice, stake, confirmedAt: null, txRef: null,
            verification: 'practice-local', result, account: null,
            url: marketUrl(m.market_id),
          }} />
      )}
    </>
  )
}
