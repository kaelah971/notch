import { Outlet } from 'react-router-dom'
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
      <div className="shell-wallet"><WalletButton /></div>
      <main id="main" className="shell-main"><Outlet /></main>
      <TabBar />
    </div>
  )
}
