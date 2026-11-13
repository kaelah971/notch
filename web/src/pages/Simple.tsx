import { Link } from 'react-router-dom'
import { ChevronRight, User, SlidersHorizontal, Swords, Dices } from 'lucide-react'
import { Unavailable } from '../components/States'
import './Simple.css'

export function Leaderboard() {
  return (
    <>
      <header className="page-head"><div><h1>Leaderboard</h1><p>Verified performance on resolved future predictions.</p></div></header>
      <Unavailable title="No verified rankings yet">
        Rankings will appear once enough future-outcome markets have resolved and predictors opt in to public profiles. Historical demonstration markets never count toward performance.
      </Unavailable>
    </>
  )
}

export function Profile() {
  return (
    <>
      <header className="page-head"><div><h1>Profile</h1></div></header>
      <Unavailable title="Connect a wallet to set up your profile">
        Public predictor profiles are opt-in. Hiding a profile only hides it inside Notch — transactions on NEAR are public and stay visible on the blockchain.
      </Unavailable>
    </>
  )
}

export function Settings() {
  return (
    <>
      <header className="page-head"><div><h1>Settings</h1></div></header>
      <div className="ilist">
        <div className="irow"><span>Network</span><span className="dim">NEAR Testnet</span></div>
        <div className="irow"><span>Sidebar</span><span className="dim">Click the logo tile to pin</span></div>
      </div>
    </>
  )
}

/** Mobile "More": Practice, Battles, Profile, Settings. */
export function More() {
  const rows = [
    { to: '/app/practice', label: 'Practice Mode', icon: Dices },
    { to: '/app/battles', label: 'Trend Battles', icon: Swords },
    { to: '/app/profile', label: 'Profile', icon: User },
    { to: '/app/settings', label: 'Settings', icon: SlidersHorizontal },
  ]
  return (
    <>
      <header className="page-head"><div><h1>More</h1></div></header>
      <ul className="ilist">
        {rows.map(({ to, label, icon: Icon }) => (
          <li key={to}><Link className="irow" to={to}><span className="irow-l"><Icon size={20} strokeWidth={1.6} />{label}</span><ChevronRight size={18} className="dim" /></Link></li>
        ))}
      </ul>
    </>
  )
}
