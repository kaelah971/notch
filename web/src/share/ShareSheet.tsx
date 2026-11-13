import { useEffect, useRef, useState } from 'react'
import { X as Close, Link2, Download, Share2 } from 'lucide-react'
import { renderCard, toBlob, type CardSpec } from './card'
import './ShareSheet.css'

/** Public site origin for share links. Set VITE_SITE_URL in production; localhost links won't work for others. */
export const siteUrl = () => ((import.meta.env.VITE_SITE_URL as string | undefined) ?? window.location.origin).replace(/\/$/, '')
export const marketUrl = (id: string) => `${siteUrl()}/app/markets/${encodeURIComponent(id)}`
export const isLocalOrigin = () => /localhost|127\.0\.0\.1/.test(siteUrl())

export function ShareSheet({ spec, text, onClose, allowAccount, onToggleAccount }: {
  spec: CardSpec
  text: string
  onClose: () => void
  allowAccount?: boolean
  onToggleAccount?: (v: boolean) => void
}) {
  const [png, setPng] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [copied, setCopied] = useState(false)
  const dlg = useRef<HTMLDialogElement>(null)

  useEffect(() => { dlg.current?.showModal() }, [])
  useEffect(() => {
    let url: string | null = null
    renderCard(spec).then(toBlob).then((b) => { if (b) { setBlob(b); url = URL.createObjectURL(b); setPng(url) } })
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [spec])

  const enc = encodeURIComponent
  const file = blob ? new File([blob], 'notch-call.png', { type: 'image/png' }) : null
  const canNative = typeof navigator.share === 'function'

  async function nativeShare() {
    try {
      if (file && navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], text, url: spec.url })
      else await navigator.share({ text, url: spec.url })
    } catch { /* user cancelled */ }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(spec.url); setCopied(true); setTimeout(() => setCopied(false), 1800) } catch { /* clipboard blocked */ }
  }

  return (
    <dialog ref={dlg} className="share" onClose={onClose} onClick={(e) => { if (e.target === dlg.current) dlg.current?.close() }} aria-label="Share">
      <div className="share-in">
        <div className="share-head">
          <h2>{spec.kind === 'call' ? 'Share my call' : 'Share market'}</h2>
          <button className="share-x" onClick={() => dlg.current?.close()} aria-label="Close"><Close size={18} /></button>
        </div>
        {png ? <img className="share-img" src={png} alt="Share card preview" /> : <div className="skeleton share-img" />}
        {spec.kind === 'call' && onToggleAccount && (
          <label className="share-opt"><input type="checkbox" checked={!!allowAccount} onChange={(e) => onToggleAccount(e.target.checked)} /> Show my NEAR account on the card</label>
        )}
        {isLocalOrigin() && <p className="fine err">This link points to a local dev server. Share links work for others once Notch is deployed (set VITE_SITE_URL).</p>}
        <div className="share-grid">
          {canNative && <button className="btn btn-primary" onClick={nativeShare}><Share2 size={16} /> Share…</button>}
          <a className="btn btn-quiet" target="_blank" rel="noreferrer" href={`https://x.com/intent/post?text=${enc(text)}&url=${enc(spec.url)}`}>Post on X</a>
          <a className="btn btn-quiet" target="_blank" rel="noreferrer" href={`https://t.me/share/url?url=${enc(spec.url)}&text=${enc(text)}`}>Telegram</a>
          <a className="btn btn-quiet" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${enc(`${text} ${spec.url}`)}`}>WhatsApp</a>
          <button className="btn btn-quiet" onClick={copy}><Link2 size={16} /> {copied ? 'Copied' : 'Copy link'}</button>
          {png && <a className="btn btn-quiet" href={png} download={spec.kind === 'call' ? 'notch-my-call.png' : 'notch-market.png'}><Download size={16} /> PNG</a>}
        </div>
      </div>
    </dialog>
  )
}
