import { Link } from 'react-router-dom'
import './Footer.css'

const product = [
  { to: '/app/markets', label: 'Markets' },
  { to: '/app/radar', label: 'Radar' },
  { to: '/app/battles', label: 'Battles' },
  { to: '/app/portfolio', label: 'Portfolio' },
]
const learn = [
  { to: '/how-it-works', label: 'How it works' },
  { to: '/how-it-works#rules', label: 'Market rules' },
  { to: '/how-it-works#evidence', label: 'Evidence & resolution' },
  { to: '/how-it-works#risk', label: 'Risk information' },
]

export function Footer({ compact = false }: { compact?: boolean }) {
  return (
    <footer className={`foot${compact ? ' is-compact' : ''}`}>
      <div className="foot-top">
        <div className="foot-brand">
          <Link to="/" className="foot-word" aria-label="Notch home">notch</Link>
          <p className="foot-tag">The internet moves. Make your call.</p>
          <p className="foot-desc">Prediction markets on public attention. Every market runs on a frozen data rule and settles from evidence anyone can check.</p>
        </div>
        <nav className="foot-cols" aria-label="Footer">
          <div><h2>Product</h2><ul>{product.map((l) => <li key={l.to}><Link to={l.to}>{l.label}</Link></li>)}</ul></div>
          <div><h2>Learn</h2><ul>{learn.map((l) => <li key={l.to}><Link to={l.to}>{l.label}</Link></li>)}</ul></div>
        </nav>
      </div>
      <div className="foot-bottom">
        <span>Built on NEAR · Testnet only — test assets have no value.</span>
        <span>© 2026 Notch</span>
      </div>
    </footer>
  )
}
