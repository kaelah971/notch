import { Link } from 'react-router-dom'
import { useWallet } from './WalletProvider'

export function WalletButton({ className = 'btn btn-quiet wb' }: { className?: string }) {
  const { ready, accountId, connect } = useWallet()
  if (accountId) {
    return <Link to="/app/portfolio" className={className} title={accountId}><span className="wb-dot" aria-hidden />{shortAccount(accountId)}</Link>
  }
  return <button type="button" className={className} onClick={connect} disabled={!ready}>Connect Wallet</button>
}

export function shortAccount(id: string) {
  return id.length > 22 ? `${id.slice(0, 8)}…${id.slice(-10)}` : id
}
