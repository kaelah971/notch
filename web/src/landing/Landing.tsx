import { Link, NavLink } from 'react-router-dom'
import { NotchMark } from '../components/icons'
import { Orbit } from './Orbit'
import { FeaturedMarkets } from './FeaturedMarkets'
import { collectibles } from './collectibles'
import { useWallet } from '../wallet/WalletProvider'
import { WalletButton } from '../wallet/WalletButton'
import './Landing.css'

export function Landing() {
  const { accountId, connect, ready } = useWallet()
  return (
    <div className="landing">
      <header className="lnav">
        <Link to="/" className="lnav-logo" aria-label="Notch home"><NotchMark width={26} height={26} /></Link>
        <nav className="lnav-pills" aria-label="Site">
          <NavLink to="/app/markets">Markets</NavLink>
          <NavLink to="/app/radar">Radar</NavLink>
          <NavLink to="/app/battles">Battles</NavLink>
        </nav>
        <WalletButton className="btn btn-white lnav-cta" />
      </header>

      <section className="hero">
        <Orbit items={collectibles} />
        <div className="hero-copy">
          <h1>The internet moves.<br />Make your call.</h1>
          <p>Discover what's gaining attention. Predict what happens next. Verify every outcome.</p>
          <Link to="/app/markets" className="btn btn-white hero-cta">Explore Markets</Link>
          {!accountId && <button type="button" className="hero-secondary" onClick={connect} disabled={!ready}>Connect Wallet</button>}
        </div>
      </section>

      <FeaturedMarkets />

      <footer className="lfoot">
        <span>Notch runs on NEAR Testnet. Test assets have no value.</span>
      </footer>
    </div>
  )
}
