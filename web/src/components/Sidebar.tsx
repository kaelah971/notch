import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { NotchMark } from './icons'
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
  return (
    <li>
      <NavLink to={item.to} className={({ isActive }) => `sb-item${isActive ? ' is-active' : ''}`} aria-label={item.label}>
        <span className="sb-icon"><Icon width={22} height={22} strokeWidth={1.6} /></span>
        <span className="sb-label">{item.label}</span>
      </NavLink>
    </li>
  )
}

/** Ref 04: tall floating pill. Hover or keyboard focus expands; the logo tile toggles a remembered pin. */
export function Sidebar({ pinned, onTogglePin }: { pinned: boolean; onTogglePin: () => void }) {
  return (
    <nav className={`sidebar${pinned ? ' is-pinned' : ''}`} aria-label="Primary">
      <div className="sb-head">
        <button
          type="button"
          className="sb-logo"
          onClick={onTogglePin}
          aria-pressed={pinned}
          aria-label={pinned ? 'Collapse sidebar' : 'Keep sidebar expanded'}
          title={pinned ? 'Collapse sidebar' : 'Keep sidebar expanded'}
        >
          <span className="sb-icon"><NotchMark /></span>
        </button>
        <span className="sb-wordmark">notch</span>
      </div>
      <hr className="sb-rule" />
      <ul className="sb-list">{primaryNav.map((i) => <Item key={i.to} item={i} />)}</ul>
      <hr className="sb-rule sb-rule-bottom" />
      <ul className="sb-list">{accountNav.map((i) => <Item key={i.to} item={i} />)}</ul>
    </nav>
  )
}
