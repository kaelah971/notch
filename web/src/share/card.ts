// Canvas-rendered Notch share cards (1200×630, the Open Graph aspect). No external deps.

import type { PredictionStatus } from '../api/types'

export interface MarketCardSpec {
  kind: 'market'
  title: string
  choices: string[]
  status: string
  deadline: string
  url: string
}
export interface CallCardSpec {
  kind: 'call'
  title: string
  choice: string
  stake: string // formatted test-USDC or practice credits, depending on verification
  confirmedAt: string | null // ISO, only when a confirmation time is actually known
  txRef: string | null // tx hash when known
  verification: 'tx' | 'contract-read' | 'practice-local'
  result?: {
    status: PredictionStatus
    outcome: string | null
    evidenceHash?: string | null
    marketId?: string
  }
  account: string | null // only when the user opts in
  url: string
}
export type CardSpec = MarketCardSpec | CallCardSpec

const Y = '#fceb53'
const W = 1200, H = 630

export function callCardBadge(spec: CallCardSpec): string {
  const txVerified = spec.verification === 'tx' && Boolean(spec.txRef?.trim())
  if (spec.verification === 'practice-local') {
    return spec.result?.status === 'CORRECT'
      ? 'Practice · correct'
      : spec.result?.status === 'INCORRECT'
        ? 'Practice · incorrect'
        : spec.result?.status === 'VOIDED'
          ? 'Practice · voided'
          : spec.result?.status === 'UNKNOWN'
            ? 'Practice · unknown'
            : 'Practice · pending'
  }
  return spec.result?.status === 'CORRECT'
    ? '✓ Prediction correct'
    : spec.result?.status === 'INCORRECT'
      ? '✕ Prediction incorrect'
      : spec.result?.status === 'VOIDED'
        ? '↺ Prediction voided'
        : spec.result?.status === 'UNKNOWN'
          ? '? Result unavailable'
          : txVerified ? '✓ Confirmed onchain' : '✓ Position verified onchain'
}

export function callCardOutcomeSuffix(spec: CallCardSpec): string {
  return spec.result?.status === 'CORRECT' && spec.result.outcome
    ? ` · final ${spec.result.outcome}`
    : spec.result?.status === 'INCORRECT' && spec.result.outcome
      ? ` · final ${spec.result.outcome}`
      : spec.result?.status === 'VOIDED' ? ' · refunded' : ''
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxW: number, maxLines: number): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w
    if (ctx.measureText(next).width > maxW && cur) { lines.push(cur); cur = w } else cur = next
  }
  if (cur) lines.push(cur)
  if (lines.length > maxLines) { lines.length = maxLines; lines[maxLines - 1] = lines[maxLines - 1].replace(/\s*\S*$/, '…') }
  return lines
}

/** Break a long identifier without truncating it; account visibility is an explicit user choice. */
function wrapToken(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const lines: string[] = []
  let current = ''
  for (const token of text.split(/\s+/)) {
    const candidate = current ? `${current} ${token}` : token
    if (ctx.measureText(candidate).width <= maxW) {
      current = candidate
      continue
    }
    if (current) lines.push(current)
    if (ctx.measureText(token).width <= maxW) {
      current = token
      continue
    }
    let chunk = ''
    for (const char of token) {
      if (ctx.measureText(chunk + char).width > maxW && chunk) {
        lines.push(chunk)
        chunk = char
      } else {
        chunk += char
      }
    }
    current = chunk
  }
  if (current) lines.push(current)
  return lines
}

function pill(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, fill: string, color: string, size = 26) {
  ctx.font = `700 ${size}px "Hanken Grotesk Variable", system-ui, sans-serif`
  const w = ctx.measureText(text).width + size * 1.4
  const h = size * 1.8
  ctx.fillStyle = fill
  ctx.beginPath(); ctx.roundRect(x, y, w, h, h / 2); ctx.fill()
  ctx.fillStyle = color
  ctx.fillText(text, x + size * 0.7, y + h * 0.66)
  return w
}

export async function renderCard(spec: CardSpec): Promise<HTMLCanvasElement> {
  // Canvas doesn't trigger font loads; request the faces explicitly so the PNG uses them.
  await Promise.all(['420 58px "Hanken Grotesk Variable"', '700 34px "Hanken Grotesk Variable"', '500 20px "Geist Mono Variable"']
    .map((f) => document.fonts?.load(f).catch(() => null)))
  const c = document.createElement('canvas')
  c.width = W; c.height = H
  const ctx = c.getContext('2d')!

  // Background: black with a soft Sunburst glow (echoes the hero).
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H)
  const g = ctx.createRadialGradient(W * 0.9, H * 1.1, 20, W * 0.9, H * 1.1, 620)
  g.addColorStop(0, 'rgba(252,235,83,.35)'); g.addColorStop(1, 'rgba(252,235,83,0)')
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)

  // Wordmark
  ctx.fillStyle = Y
  ctx.font = '640 56px "Hanken Grotesk Variable", system-ui, sans-serif'
  ctx.fillText('notch', 64, 104)
  ctx.font = '500 22px "Hanken Grotesk Variable", system-ui, sans-serif'
  ctx.fillStyle = 'rgba(235,235,245,.6)'
  ctx.fillText('NEAR Testnet · Wikipedia attention markets', 64, 140)

  let y = 220
  if (spec.kind === 'call') {
    pill(ctx, 64, y - 44, callCardBadge(spec), 'rgba(252,235,83,.16)', Y, 22)
    y += 30
  } else {
    pill(ctx, 64, y - 44, spec.status, 'rgba(255,255,255,.1)', '#fff', 22)
    y += 30
  }

  ctx.fillStyle = '#fff'
  ctx.font = '420 58px "Hanken Grotesk Variable", system-ui, sans-serif'
  for (const line of wrap(ctx, spec.title, W - 128, 3)) { ctx.fillText(line, 64, y + 40); y += 68 }
  y += 24

  if (spec.kind === 'call') {
    const practice = spec.verification === 'practice-local'
    const txVerified = spec.verification === 'tx' && Boolean(spec.txRef?.trim())
    ctx.font = '500 26px "Hanken Grotesk Variable", system-ui, sans-serif'; ctx.fillStyle = 'rgba(235,235,245,.6)'
    ctx.fillText(practice ? 'Practice call' : 'My call', 64, y + 20)
    const w = pill(ctx, 64, y + 36, spec.choice, Y, '#0a0a0a', 34)
    ctx.font = '700 34px "Hanken Grotesk Variable", system-ui, sans-serif'; ctx.fillStyle = '#fff'
    ctx.fillText(`${spec.stake} ${practice ? 'practice credits' : 'test-USDC'}${callCardOutcomeSuffix(spec)}`, 64 + w + 24, y + 36 + 42)
    ctx.font = '500 20px "Geist Mono Variable", ui-monospace, monospace'; ctx.fillStyle = 'rgba(235,235,245,.5)'
    const ref = practice
      ? spec.result?.status === 'PENDING' ? 'practice record · market not finalized'
        : spec.result?.status === 'UNKNOWN' ? 'practice record · evidence unavailable'
          : 'practice record · local-only'
      : txVerified ? `tx ${spec.txRef!.slice(0, 10)}…${spec.txRef!.slice(-6)}`
        : spec.result?.status === 'PENDING' ? 'market not finalized'
          : spec.result?.status === 'VOIDED' ? 'market voided or refunded'
            : 'verified by market contract read'
    const evidence = spec.result?.evidenceHash
      ? ` · evidence ${spec.result.evidenceHash.slice(0, 12)}…${spec.result.evidenceHash.slice(-6)}`
      : ''
    const callBaseline = y + 36 + 42
    const ctaY = H - 44
    const metaY = Math.max(callBaseline + 30, spec.account ? ctaY - 60 : ctaY - 48)
    const confirmed = spec.confirmedAt ? `${new Date(spec.confirmedAt).toISOString().slice(0, 16).replace('T', ' ')} UTC · ` : ''
    ctx.fillText(`${confirmed}${ref}${evidence}`, 64, metaY)
    if (spec.account) {
      for (const [i, line] of wrapToken(ctx, `Account · ${spec.account}`, W - 128).entries()) {
        ctx.fillText(line, 64, metaY + 28 + i * 22)
      }
    }
    ctx.font = '700 28px "Hanken Grotesk Variable", system-ui, sans-serif'; ctx.fillStyle = Y
    ctx.fillText(practice ? 'Practice only · no wallet required' : 'Think I’m wrong? Make your call.', 64, H - 44)
  } else {
    let x = 64
    for (const ch of spec.choices) x += pill(ctx, x, y, ch, 'rgba(255,255,255,.1)', '#fff', 30) + 14
    ctx.font = '500 22px "Hanken Grotesk Variable", system-ui, sans-serif'; ctx.fillStyle = 'rgba(235,235,245,.6)'
    ctx.fillText(`${spec.deadline} · Settles from Wikimedia Pageviews evidence`, 64, H - 92)
    ctx.font = '700 28px "Hanken Grotesk Variable", system-ui, sans-serif'; ctx.fillStyle = Y
    ctx.fillText('Make your call →', 64, H - 44)
  }
  ctx.font = '500 20px "Hanken Grotesk Variable", system-ui, sans-serif'; ctx.fillStyle = 'rgba(235,235,245,.45)'
  const u = spec.url.replace(/^https?:\/\//, '')
  ctx.fillText(u.length > 60 ? u.slice(0, 59) + '…' : u, W - 64 - Math.min(ctx.measureText(u).width, 640), 104)
  return c
}

export const toBlob = (c: HTMLCanvasElement) => new Promise<Blob | null>((r) => c.toBlob(r, 'image/png'))
