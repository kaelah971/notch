import { Radar, Swords, Wallet, Trophy, User, SlidersHorizontal, Ellipsis, Dices, type LucideIcon } from 'lucide-react'
import { MarketsIcon } from './icons'
import type { ComponentType, SVGProps } from 'react'

export type NavIcon = LucideIcon | ComponentType<SVGProps<SVGSVGElement>>
export interface NavItem { to: string; label: string; icon: NavIcon }

// Desktop sidebar (ref 04): primary group, divider, account group.
export const primaryNav: NavItem[] = [
  { to: '/app/markets', label: 'Markets', icon: MarketsIcon },
  { to: '/app/practice', label: 'Practice Mode', icon: Dices },
  { to: '/app/discover', label: 'Discover', icon: Radar },
  { to: '/app/strategy-builder', label: 'Strategy Builder', icon: SlidersHorizontal },
  { to: '/app/battles', label: 'Trend Battles', icon: Swords },
  { to: '/app/portfolio', label: 'Portfolio', icon: Wallet },
  { to: '/app/leaderboard', label: 'Leaderboard', icon: Trophy },
]
export const accountNav: NavItem[] = [
  { to: '/app/profile', label: 'Profile', icon: User },
  { to: '/app/settings', label: 'Settings', icon: SlidersHorizontal },
]

// Mobile tab bar. Battles lives inside Markets; Profile/Settings under More.
export const mobileTabs: NavItem[] = [
  { to: '/app/markets', label: 'Markets', icon: MarketsIcon },
  { to: '/app/discover', label: 'Discover', icon: Radar },
  { to: '/app/portfolio', label: 'Portfolio', icon: Wallet },
  { to: '/app/leaderboard', label: 'Leaderboard', icon: Trophy },
  { to: '/app/more', label: 'More', icon: Ellipsis },
]
