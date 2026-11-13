import type { Position, PredictionStatus } from './types'

export const PREDICTION_STATUS_LABEL: Record<PredictionStatus, string> = {
  PENDING: 'Pending',
  CORRECT: 'Correct',
  INCORRECT: 'Incorrect',
  VOIDED: 'Voided',
  UNKNOWN: 'Result unavailable',
}

export const PREDICTION_STATUS_HELP: Record<PredictionStatus, string> = {
  PENDING: 'The market has not finalized.',
  CORRECT: 'Your recorded call matches the finalized outcome.',
  INCORRECT: 'Your recorded call differs from the finalized outcome.',
  VOIDED: 'The market was voided or refunded; it is excluded from accuracy.',
  UNKNOWN: 'The finalized outcome or original call could not be verified reliably.',
}

const STATUSES = new Set<PredictionStatus>(['PENDING', 'CORRECT', 'INCORRECT', 'VOIDED', 'UNKNOWN'])

export function predictionStatus(p: Pick<Position, 'prediction_status'>): PredictionStatus {
  return STATUSES.has(p.prediction_status) ? p.prediction_status : 'UNKNOWN'
}

export function predictionBadgeClass(status: PredictionStatus): string {
  return `result-${status.toLowerCase()}`
}

export function selectedChoices(p: Pick<Position, 'prediction_choices' | 'prediction_choice'>): string[] {
  if (Array.isArray(p.prediction_choices) && p.prediction_choices.length) return p.prediction_choices
  return p.prediction_choice ? [p.prediction_choice] : []
}

export interface ForecastPassport {
  total: number
  correct: number
  incorrect: number
  pending: number
  voided: number
  unknown: number
  completed: number
  accuracy: number | null
}

export function summarizeForecast(rows: ReadonlyArray<Pick<Position, 'prediction_status'>>): ForecastPassport {
  const counts = { total: rows.length, correct: 0, incorrect: 0, pending: 0, voided: 0, unknown: 0 }
  for (const row of rows) {
    switch (predictionStatus(row)) {
      case 'CORRECT': counts.correct += 1; break
      case 'INCORRECT': counts.incorrect += 1; break
      case 'PENDING': counts.pending += 1; break
      case 'VOIDED': counts.voided += 1; break
      case 'UNKNOWN': counts.unknown += 1; break
    }
  }
  const completed = counts.correct + counts.incorrect
  return {
    ...counts,
    completed,
    accuracy: completed ? counts.correct / completed * 100 : null,
  }
}

export function shortEvidence(value: string | null | undefined): string | null {
  if (!value) return null
  return value.length > 24 ? `${value.slice(0, 16)}…${value.slice(-6)}` : value
}
