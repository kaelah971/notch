import { api } from '../api/client'
import type { SignedMessageResult } from '../wallet/WalletProvider'

export const CREATOR_SESSION_KEY = 'notch.creator-studio.session.v1'
export const CREATOR_SESSION_EVENT = 'notch:creator-session'
export type StoredCreatorSession = { token: string; accountId: string; expiresAt: string }

function notifySessionChange() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(CREATOR_SESSION_EVENT))
}
type SignMessage = (params: { message: string; recipient: string; nonce: Uint8Array }) => Promise<SignedMessageResult>

export function readCreatorSession(): StoredCreatorSession | null {
  try {
    const value = JSON.parse(localStorage.getItem(CREATOR_SESSION_KEY) ?? 'null') as StoredCreatorSession | null
    if (!value?.token || !value.accountId || !value.expiresAt || Date.parse(value.expiresAt) <= Date.now()) return null
    return value
  } catch {
    return null
  }
}

export function clearCreatorSession() {
  localStorage.removeItem(CREATOR_SESSION_KEY)
  notifySessionChange()
}

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value)
  return Uint8Array.from(binary, (char) => char.charCodeAt(0))
}

export async function verifyCreatorOwnership(accountId: string, signMessage: SignMessage): Promise<StoredCreatorSession> {
  const challenge = (await api.creatorChallenge(accountId)).data
  const signed = await signMessage({
    message: challenge.message,
    recipient: challenge.recipient,
    nonce: decodeBase64(challenge.nonce_b64),
  })
  if (signed.accountId !== accountId) throw new Error('The wallet signed for a different account.')
  const verified = (await api.creatorVerify({
    challenge_id: challenge.challenge_id,
    account_id: accountId,
    public_key: signed.publicKey,
    signature: signed.signature,
  })).data
  const session = { token: verified.session_token, accountId: verified.account_id, expiresAt: verified.session_expires_at }
  localStorage.setItem(CREATOR_SESSION_KEY, JSON.stringify(session))
  notifySessionChange()
  return session
}
