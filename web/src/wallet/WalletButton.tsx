import { Link } from 'react-router-dom'
import { useWallet } from './WalletProvider'

export function WalletButton({ className = 'btn btn-quiet wb' }: { className?: string }) {
  const { ready, accountId, connect, initError, retryInit } = useWallet()
  if (accountId) {
    return <Link to="/app/portfolio" className={className} title={accountId}><span className="wb-dot" aria-hidden />{shortAccount(accountId)}</Link>
  }
  if (initError) {
    return <button type="button" className={className} onClick={retryInit} title={initError}>Wallet unavailable · Retry</button>
  }
  return <button type="button" className={className} onClick={connect} disabled={!ready} title={ready ? 'Connect Meteor, Nightly, or Sender (NEAR Testnet)' : 'Loading wallet…'}>{ready ? 'Connect Wallet' : 'Loading wallet…'}</button>
}

export function shortAccount(id: string) {
  return id.length > 22 ? `${id.slice(0, 8)}…${id.slice(-10)}` : id
}
