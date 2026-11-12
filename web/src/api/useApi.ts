import { useCallback, useEffect, useState } from 'react'
import { ApiError } from './client'

export type Loadable<T> = { status: 'loading' } | { status: 'error'; error: ApiError } | { status: 'ok'; data: T }

export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): [Loadable<T>, () => void] {
  const [state, setState] = useState<Loadable<T>>({ status: 'loading' })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => {
    let live = true
    setState({ status: 'loading' })
    fn().then(
      (data) => { if (live) setState({ status: 'ok', data }) },
      (e) => { if (live) setState({ status: 'error', error: e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e)) }) },
    )
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return [state, reload]
}
