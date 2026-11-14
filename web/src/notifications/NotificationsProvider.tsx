import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import type { Notification, NotificationMeta } from '../api/types'
import { clearCreatorSession, CREATOR_SESSION_EVENT, readCreatorSession, type StoredCreatorSession } from '../creator/session'
import { useWallet } from '../wallet/WalletProvider'

interface NotificationsContextValue {
  session: StoredCreatorSession | null
  notifications: Notification[]
  unreadCount: number
  reconciliation: NotificationMeta['reconciliation'] | null
  loading: boolean
  error: ApiError | null
  refresh: () => Promise<void>
  markRead: (notificationId: string) => Promise<void>
  markAllRead: () => Promise<void>
}

const NotificationsContext = createContext<NotificationsContextValue | null>(null)

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { accountId } = useWallet()
  const [session, setSession] = useState<StoredCreatorSession | null>(() => readCreatorSession())
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [reconciliation, setReconciliation] = useState<NotificationMeta['reconciliation'] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const refresh = useCallback(async () => {
    if (!session) {
      setNotifications([])
      setUnreadCount(0)
      setReconciliation(null)
      setError(null)
      return
    }
    setLoading(true)
    try {
      const result = await api.notifications(session.token)
      if (!result.meta) throw new ApiError(0, 'INVALID_RESPONSE', 'The notification inbox response was incomplete.')
      setNotifications(result.data)
      setUnreadCount(result.meta.unread_count)
      setReconciliation(result.meta.reconciliation)
      setError(null)
    } catch (value) {
      setError(value instanceof ApiError ? value : new ApiError(0, 'UNKNOWN', String(value)))
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    if (session && accountId && session.accountId !== accountId) {
      clearCreatorSession()
      setSession(null)
    }
  }, [accountId, session])

  useEffect(() => {
    const updateSession = () => setSession(readCreatorSession())
    window.addEventListener(CREATOR_SESSION_EVENT, updateSession)
    window.addEventListener('storage', updateSession)
    window.addEventListener('focus', refresh)
    return () => {
      window.removeEventListener(CREATOR_SESSION_EVENT, updateSession)
      window.removeEventListener('storage', updateSession)
      window.removeEventListener('focus', refresh)
    }
  }, [refresh])

  useEffect(() => { void refresh() }, [refresh])

  const value = useMemo<NotificationsContextValue>(() => ({
    session,
    notifications,
    unreadCount,
    reconciliation,
    loading,
    error,
    refresh,
    markRead: async (notificationId) => {
      if (!session) return
      await api.notificationRead(session.token, notificationId)
      await refresh()
    },
    markAllRead: async () => {
      if (!session) return
      await api.notificationsReadAll(session.token)
      await refresh()
    },
  }), [error, loading, notifications, reconciliation, refresh, session, unreadCount])

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>
}

export function useNotifications(): NotificationsContextValue {
  const context = useContext(NotificationsContext)
  if (!context) throw new Error('useNotifications must be used inside NotificationsProvider')
  return context
}
