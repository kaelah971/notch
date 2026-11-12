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
import { Leaderboard, More, Profile, Settings } from './pages/Simple'
import { Portfolio } from './pages/Portfolio'

const router = createBrowserRouter([
  { path: '/', element: <Landing /> },
  {
    path: '/app',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="markets" replace /> },
      { path: 'markets', element: <Markets /> },
      { path: 'markets/:id', element: <MarketDetail /> },
      { path: 'battles', element: <Markets battlesOnly /> },
      { path: 'radar', element: <Radar /> },
      { path: 'portfolio', element: <Portfolio /> },
      { path: 'leaderboard', element: <Leaderboard /> },
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
