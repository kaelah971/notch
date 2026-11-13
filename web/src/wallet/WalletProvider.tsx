import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { WalletSelector } from '@near-wallet-selector/core'
import type { WalletSelectorModal } from '@near-wallet-selector/modal-ui'
import './wallet-modal.css'

// Wallet SDKs are large; load them after first paint so the landing page stays light.
const loadSdk = () => import('./sdk')

export interface FunctionCall { methodName: string; args: object; gasTgas: number; depositYocto: string }
/** One transaction to one receiver; several calls become several actions in the same signed transaction. */
export interface FunctionCallTx { receiverId: string; calls: FunctionCall[] }

export interface TxResult {
  /** Present for wallets that return an outcome in-page. Redirect wallets return via URL instead. */
  hash: string | null
  redirected: boolean
}

interface WalletCtx {
  ready: boolean
  /** Set when the wallet SDK failed to initialise; shown to the user with a retry. */
  initError: string | null
  retryInit: () => void
  accountId: string | null
  connect: () => void
  disconnect: () => Promise<void>
  /** Asks the user's wallet to sign and send. Notch never signs. */
  signAndSend: (tx: FunctionCallTx) => Promise<TxResult>
}

const Ctx = createContext<WalletCtx | null>(null)

export function WalletProvider({ children }: { children: ReactNode }) {
  const [selector, setSelector] = useState<WalletSelector | null>(null)
  const [modal, setModal] = useState<WalletSelectorModal | null>(null)
  const [accountId, setAccountId] = useState<string | null>(null)
  const [initError, setInitError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let sub: { unsubscribe: () => void } | undefined
    let cancelled = false
    loadSdk().then(({ setupWalletSelector, setupMeteorWallet, setupNightly, setupSender }) =>
      // Keep Meteor and Sender, and add the official Nightly Testnet connector.
      setupWalletSelector({
        network: 'testnet',
        modules: [setupMeteorWallet(), setupNightly(), setupSender()],
      }),
    ).then(async (s) => {
      if (cancelled) return
      const { setupModal } = await loadSdk()
      // No contractId: entries need a 1-yocto deposit, so every call is a full-access signature in the user's wallet.
      setModal(setupModal(s, { theme: 'dark', description: 'Connect Meteor, Nightly, or Sender on NEAR Testnet. Notch never holds your keys — you approve every transaction in your wallet.' }))
      setSelector(s)
      const pick = () => s.store.getState().accounts.find((a) => a.active)?.accountId ?? null
      setAccountId(pick())
      sub = s.store.observable.subscribe(() => setAccountId(pick()))
      setInitError(null)
    }).catch((e) => {
      console.error('wallet selector failed', e)
      if (!cancelled) setInitError(explainWalletError(e))
    })
    return () => { cancelled = true; sub?.unsubscribe() }
  }, [attempt])
  const retryInit = useCallback(() => setAttempt((a) => a + 1), [])

  const connect = useCallback(() => modal?.show(), [modal])

  const disconnect = useCallback(async () => {
    if (!selector) return
    const w = await selector.wallet()
    await w.signOut()
  }, [selector])

  const signAndSend = useCallback(async (tx: FunctionCallTx): Promise<TxResult> => {
    if (!selector || !accountId) throw new Error('Connect a wallet first.')
    const { actionCreators } = await loadSdk()
    const w = await selector.wallet()
    let outcome
    try {
      outcome = await w.signAndSendTransaction({
        signerId: accountId,
        receiverId: tx.receiverId,
        actions: tx.calls.map((c) => actionCreators.functionCall(c.methodName, c.args, BigInt(c.gasTgas) * 10n ** 12n, BigInt(c.depositYocto))),
      })
    } catch (e) {
      throw new Error(explainWalletError(e))
    }
    if (!outcome) return { hash: null, redirected: true }
    const failure = (outcome.status as { Failure?: unknown })?.Failure
    if (failure) throw new Error(`Transaction failed onchain: ${JSON.stringify(failure)}`)
    return { hash: outcome.transaction_outcome?.id ?? outcome.transaction?.hash ?? null, redirected: false }
  }, [selector, accountId])

  const value = useMemo(() => ({ ready: !!selector, initError, retryInit, accountId, connect, disconnect, signAndSend }), [selector, initError, retryInit, accountId, connect, disconnect, signAndSend])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useWallet(): WalletCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useWallet outside WalletProvider')
  return c
}

export const explorerTx = (hash: string) => `https://testnet.nearblocks.io/txns/${hash}`
export const explorerAccount = (id: string) => `https://testnet.nearblocks.io/address/${id}`

/** Turn wallet/SDK errors into a next step the user can act on. Keeps the raw text for support. */
export function explainWalletError(e: unknown): string {
  const raw = e instanceof Error ? e.message : typeof e === 'string' ? e : JSON.stringify(e)
  const m = raw.toLowerCase()
  if (/process is not defined|buffer is not defined|global is not defined/.test(m))
    return 'The wallet library failed to load in this browser. Hard-refresh the page (Ctrl+Shift+R) and try again.'
  if (/reject|denied|cancel|closed|user (did not|didn.t)/.test(m))
    return 'You cancelled the wallet request. Nothing was signed or sent.'
  if (/not injected|extension.*not found|not installed|not available/.test(m))
    return 'The selected wallet is not available in this browser. Install or enable it, then retry.'
  if (/no account|not signed in|not connected|wallet not found|no wallet/.test(m))
    return 'A wallet isn’t connected. Click Connect Wallet, choose Meteor, Nightly, or Sender, and approve the connection on NEAR Testnet.'
  if (/network|testnet|mainnet|wrong chain/.test(m) && /mismatch|wrong|unsupported/.test(m))
    return 'The selected wallet is on the wrong network. Switch it to NEAR Testnet and try again.'
  if (/not enough balance|notenoughbalance|insufficient|lackbalance/.test(m))
    return 'Your testnet account doesn’t have enough NEAR to pay for this transaction. Top up from the NEAR testnet faucet and retry.'
  if (/endpoint has been discontinued|lavanet/.test(m))
    return 'Sender Wallet reported a discontinued RPC endpoint. Notch sent a NEAR Testnet request; this failure is inside Sender’s extension RPC path, not Notch or the contract. Use a supported alternative wallet or a Sender release that fixes its Testnet RPC state.'
  if (/failed to fetch|timeout|timed out|rpc/.test(m))
    return 'The NEAR testnet RPC didn’t respond. Check your connection and try again in a moment.'
  return `Wallet error: ${raw}`
}
