import { NavLink } from 'react-router-dom'
import { useNotifications } from '../notifications/NotificationsProvider'
import { mobileTabs } from './nav'
import './TabBar.css'

/** Mobile: iOS-style floating bottom tab bar. */
export function TabBar() {
  const { unreadCount } = useNotifications()
  return (
    <nav className="tabbar" aria-label="Primary">
      <ul>
        {mobileTabs.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink to={to} className={({ isActive }) => `tab${isActive ? ' is-active' : ''}`}>
              <span className="tab-icon-wrap"><Icon width={22} height={22} strokeWidth={1.6} />{to === '/app/notifications' && unreadCount > 0 && <span className="tab-badge" aria-label={`${unreadCount} unread`}>{unreadCount > 9 ? '9+' : unreadCount}</span>}</span>
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
