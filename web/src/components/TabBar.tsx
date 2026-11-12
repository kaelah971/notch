import { NavLink } from 'react-router-dom'
import { mobileTabs } from './nav'
import './TabBar.css'

/** Mobile: iOS-style floating bottom tab bar. */
export function TabBar() {
  return (
    <nav className="tabbar" aria-label="Primary">
      <ul>
        {mobileTabs.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink to={to} className={({ isActive }) => `tab${isActive ? ' is-active' : ''}`}>
              <Icon width={22} height={22} strokeWidth={1.6} />
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
