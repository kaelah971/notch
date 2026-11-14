import { useEffect, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Pin, PinOff } from 'lucide-react'
import { NotchMark } from './icons'
import { useNotifications } from '../notifications/NotificationsProvider'
import { accountNav, primaryNav, type NavItem } from './nav'
import './Sidebar.css'

const PIN_KEY = 'notch.sidebar.pinned'

function readPinned(): boolean {
  try { return localStorage.getItem(PIN_KEY) === '1' } catch { return false }
}

export function useSidebarPinned() {
  const [pinned, setPinned] = useState(readPinned)
  useEffect(() => {
    try { localStorage.setItem(PIN_KEY, pinned ? '1' : '0') } catch { /* storage unavailable */ }
  }, [pinned])
  return [pinned, setPinned] as const
}

function Item({ item }: { item: NavItem }) {
  const Icon = item.icon
  const { unreadCount } = useNotifications()
  const isNotifications = item.to === '/app/notifications'
  return (
    <li>
      <NavLink to={item.to} className={({ isActive }) => `sb-item${isActive ? ' is-active' : ''}`} aria-label={item.label}>
        <span className="sb-icon"><Icon width={22} height={22} strokeWidth={1.6} /></span>
        <span className="sb-label">{item.label}</span>
        {isNotifications && unreadCount > 0 && <span className="sb-badge" aria-label={`${unreadCount} unread`}>{unreadCount > 9 ? '9+' : unreadCount}</span>}
      </NavLink>
    </li>
  )
}

/** Ref 04: tall floating pill. Hover or keyboard focus expands; the logo links home; the pin button keeps it expanded (remembered). */
export function Sidebar({ pinned, onTogglePin }: { pinned: boolean; onTogglePin: () => void }) {
  return (
    <nav className={`app-sidebar${pinned ? ' is-pinned' : ''}`} aria-label="Primary">
      <div className="sb-head">
        <Link to="/" className="sb-logo" aria-label="Notch home" title="Notch home">
          <span className="sb-icon"><NotchMark /></span>
        </Link>
        <Link to="/" className="sb-wordmark" tabIndex={-1}>notch</Link>
        <button
          type="button"
          className="sb-pin"
          onClick={onTogglePin}
          aria-pressed={pinned}
          aria-label={pinned ? 'Unpin sidebar' : 'Pin sidebar open'}
          title={pinned ? 'Unpin sidebar' : 'Pin sidebar open'}
        >
          {pinned ? <PinOff size={16} /> : <Pin size={16} />}
        </button>
      </div>
      <hr className="sb-rule" />
      <ul className="sb-list">{primaryNav.map((i) => <Item key={i.to} item={i} />)}</ul>
      <hr className="sb-rule sb-rule-bottom" />
      <ul className="sb-list">{accountNav.map((i) => <Item key={i.to} item={i} />)}</ul>
    </nav>
  )
}
