import { Link, Outlet } from 'react-router-dom'
import { NotchMark } from './icons'
import { Sidebar, useSidebarPinned } from './Sidebar'
import { TabBar } from './TabBar'
import { WalletButton } from '../wallet/WalletButton'
import './AppShell.css'

export function AppShell() {
  const [pinned, setPinned] = useSidebarPinned()
  return (
    <div className={`shell${pinned ? ' is-pinned' : ''}`}>
      <a className="skip" href="#main">Skip to content</a>
      <Sidebar pinned={pinned} onTogglePin={() => setPinned((p) => !p)} />
      <Link to="/" className="shell-home" aria-label="Notch home"><NotchMark width={24} height={24} /><span>notch</span></Link>
      <div className="shell-wallet"><WalletButton /></div>
      <main id="main" className="shell-main"><Outlet /><p className="shell-legal">NEAR Testnet · test assets have no value · <Link to="/how-it-works#risk">Risk</Link> · © 2026 Notch</p></main>
      <TabBar />
    </div>
  )
}
