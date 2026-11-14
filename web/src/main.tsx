import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import './index.css'
import { WalletProvider } from './wallet/WalletProvider'
import { AppShell } from './components/AppShell'
import { Landing } from './landing/Landing'
import { Markets } from './pages/Markets'
import { MarketDetail } from './pages/MarketDetail'
import { Radar } from './pages/Radar'
import { Discover } from './pages/Discover'
import { StrategyBuilder } from './pages/StrategyBuilder'
import { StrategyLab } from './pages/StrategyLab'
import { More, Profile, Settings } from './pages/Simple'
import { SignalsHub } from './signals/SignalsHub'
import { Predictor } from './signals/Predictor'
import { Portfolio } from './pages/Portfolio'
import { HowItWorks } from './pages/HowItWorks'
import { Practice } from './pages/Practice'
import { Arena } from './pages/Arena'

const router = createBrowserRouter([
  { path: '/', element: <Landing /> },
  { path: '/how-it-works', element: <HowItWorks /> },
  {
    path: '/app',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="markets" replace /> },
      { path: 'markets', element: <Markets /> },
      { path: 'markets/:id', element: <MarketDetail /> },
      { path: 'practice', element: <Practice /> },
      { path: 'arena', element: <Arena /> },
      { path: 'battles', element: <Markets battlesOnly /> },
      { path: 'discover', element: <Discover /> },
      { path: 'strategy-builder', element: <StrategyBuilder /> },
      { path: 'strategies', element: <StrategyBuilder /> },
      { path: 'strategy-lab', element: <StrategyLab /> },
      { path: 'radar', element: <Radar /> },
      { path: 'portfolio', element: <Portfolio /> },
      { path: 'leaderboard', element: <SignalsHub /> },
      { path: 'p/:accountId', element: <Predictor /> },
      { path: 'profile', element: <Profile /> },
      { path: 'settings', element: <Settings /> },
      { path: 'more', element: <More /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode><WalletProvider><RouterProvider router={router} /></WalletProvider></StrictMode>,
)
