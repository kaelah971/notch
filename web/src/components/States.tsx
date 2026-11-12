import type { ApiError } from '../api/client'

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const msg = error.code === 'NETWORK'
    ? 'We couldn’t reach the Notch API. Check that it’s running and try again.'
    : error.status === 429 ? 'Too many requests. Wait a moment and retry.' : error.message
  return (
    <div className="state" role="alert">
      <h2>Something went wrong</h2>
      <p>{msg}</p>
      <p className="mono" style={{ fontSize: 12, marginTop: 8, color: 'var(--text-3)' }}>{error.code}</p>
      {onRetry && <button className="btn btn-quiet" style={{ marginTop: 16 }} onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function SkeletonList({ n = 3, h = 148 }: { n?: number; h?: number }) {
  return (
    <div style={{ display: 'grid', gap: 12 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: n }, (_, i) => <div key={i} className="skeleton" style={{ height: h }} />)}
    </div>
  )
}

export function Unavailable({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="state"><h2>{title}</h2><p style={{ maxWidth: 460, margin: '0 auto' }}>{children}</p></div>
}
