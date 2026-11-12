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

  useEffect(() => {
    let sub: { unsubscribe: () => void } | undefined
    let cancelled = false
    loadSdk().then(({ setupWalletSelector, setupMeteorWallet, setupMyNearWallet }) =>
      setupWalletSelector({ network: 'testnet', modules: [setupMeteorWallet(), setupMyNearWallet()] }),
    ).then(async (s) => {
      if (cancelled) return
      const { setupModal } = await loadSdk()
      // No contractId: entries need a 1-yocto deposit, so every call is a full-access signature in the user's wallet.
      setModal(setupModal(s, { theme: 'dark', description: 'Connect a NEAR Testnet wallet. Notch never holds your keys.' }))
      setSelector(s)
      const pick = () => s.store.getState().accounts.find((a) => a.active)?.accountId ?? null
      setAccountId(pick())
      sub = s.store.observable.subscribe(() => setAccountId(pick()))
    }).catch((e) => console.error('wallet selector failed', e))
    return () => { cancelled = true; sub?.unsubscribe() }
  }, [])

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
    const outcome = await w.signAndSendTransaction({
      signerId: accountId,
      receiverId: tx.receiverId,
      actions: tx.calls.map((c) => actionCreators.functionCall(c.methodName, c.args, BigInt(c.gasTgas) * 10n ** 12n, BigInt(c.depositYocto))),
    })
    if (!outcome) return { hash: null, redirected: true }
    const failure = (outcome.status as { Failure?: unknown })?.Failure
    if (failure) throw new Error(`Transaction failed onchain: ${JSON.stringify(failure)}`)
    return { hash: outcome.transaction_outcome?.id ?? outcome.transaction?.hash ?? null, redirected: false }
  }, [selector, accountId])

  const value = useMemo(() => ({ ready: !!selector, accountId, connect, disconnect, signAndSend }), [selector, accountId, connect, disconnect, signAndSend])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useWallet(): WalletCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useWallet outside WalletProvider')
  return c
}

export const explorerTx = (hash: string) => `https://testnet.nearblocks.io/txns/${hash}`
export const explorerAccount = (id: string) => `https://testnet.nearblocks.io/address/${id}`
