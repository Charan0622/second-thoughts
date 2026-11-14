// "Connect phone": show a QR to /phone on the backend; poll for the phone's latest photo and
// hand it to the same run path as a webcam capture. While the resulting run is on screen, the
// phone photo is overlaid into the camera frame so the stage shows what the council is judging.
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  onFrame: (dataUrl: string, price: number | null) => void
  /** App's run counter; the phone photo stays in the camera frame only for the run it started. */
  runId: number
}

interface Info { url: string; qr_svg: string }
interface Latest { id: number; frame: string | null; price?: number | null; ts?: number }

const KEEP_POLLING_MS = 10 * 60 * 1000

const CSS = `
.phl-btn { align-self: center; justify-self: start; width: auto; flex: 0 0 auto; font: 500 0.78rem/1 var(--sans); padding: 7px 12px; border-radius: 999px;
  border: 1px solid var(--hair-2); background: transparent; color: var(--ink-2); white-space: nowrap; }
.phl-btn:hover { border-color: var(--ink); color: var(--ink); }
.phl-btn.is-live { border-color: var(--buy); color: var(--buy); }
.phl-scrim { position: fixed; inset: 0; z-index: 60; background: rgba(22, 20, 15, 0.55); display: grid; place-items: center; padding: var(--gutter); }
.phl-card { background: var(--paper); color: var(--ink); border-radius: 10px; padding: var(--s5); width: min(380px, 100%);
  display: grid; gap: var(--s3); box-shadow: 0 20px 60px rgba(0,0,0,.35); font-family: var(--sans); }
.phl-head { display: flex; justify-content: space-between; align-items: baseline; gap: var(--s3); }
.phl-title { font: 400 1.5rem/1.1 var(--serif); }
.phl-x { background: none; border: 0; font-size: 1.3rem; line-height: 1; color: var(--ink-2); padding: 4px; }
.phl-qr { width: 100%; aspect-ratio: 1; background: #fff; border-radius: 6px; display: grid; place-items: center; overflow: hidden; }
.phl-qr svg { width: 100%; height: 100%; display: block; }
.phl-url { font: 400 0.82rem/1.3 var(--mono); color: var(--ink-2); word-break: break-all; text-align: center; }
.phl-status { font-size: 0.92rem; text-align: center; }
.phl-err { color: var(--wait); font-size: 0.86rem; text-align: center; }
.phl-hint { font-size: 0.74rem; color: var(--ink-3); text-align: center; }
.phl-photo { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
`

export default function PhoneLink({ onFrame, runId }: Props) {
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState<Info | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [received, setReceived] = useState(false)
  const [lastFrameAt, setLastFrameAt] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const [shown, setShown] = useState<{ src: string; runId: number } | null>(null)
  const lastId = useRef<number | null>(null)
  const onFrameRef = useRef(onFrame)
  onFrameRef.current = onFrame
  const runIdRef = useRef(runId)
  runIdRef.current = runId

  const polling = open || (lastFrameAt > 0 && now - lastFrameAt < KEEP_POLLING_MS)

  const show = useCallback(async () => {
    setOpen(true)
    setReceived(false)
    setError(null)
    try {
      const res = await fetch('/api/phone/info')
      if (!res.ok) throw new Error(`backend ${res.status}`)
      setInfo((await res.json()) as Info)
    } catch (e) {
      setInfo(null)
      setError(`Phone link needs the live backend (${e instanceof Error ? e.message : String(e)}).`)
    }
  }, [])

  useEffect(() => {
    if (!polling) return
    let stopped = false
    const tick = async () => {
      setNow(Date.now())
      try {
        const res = await fetch(`/api/phone/latest?after=${lastId.current ?? 0}`)
        if (!res.ok || stopped) return
        const d = (await res.json()) as Latest
        if (lastId.current === null) { lastId.current = d.id; return } // skip frames sent before we looked
        if (d.frame && d.id > lastId.current) {
          lastId.current = d.id
          setReceived(true)
          setLastFrameAt(Date.now())
          setShown({ src: d.frame, runId: runIdRef.current + 1 })
          onFrameRef.current(d.frame, d.price ?? null)
          setTimeout(() => setOpen(false), 600)
        }
      } catch { /* backend unreachable (mock mode): keep quiet */ }
    }
    void tick()
    const t = setInterval(tick, 1000)
    return () => { stopped = true; clearInterval(t) }
  }, [polling])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const frameWrap = shown && shown.runId === runId ? document.querySelector('.frame-wrap') : null

  return (
    <>
      <style>{CSS}</style>
      <button type="button" className={`phl-btn ${polling ? 'is-live' : ''}`} onClick={show} title="Take the photo with your phone">
        📱 Connect phone
      </button>
      {frameWrap && createPortal(<img className="phl-photo" src={shown!.src} alt="Photo from your phone" />, frameWrap)}
      {open && createPortal(
        <div className="phl-scrim" onClick={() => setOpen(false)}>
          <div className="phl-card" role="dialog" aria-modal="true" aria-label="Connect your phone" onClick={(e) => e.stopPropagation()}>
            <div className="phl-head">
              <span className="phl-title">Connect your phone</span>
              <button type="button" className="phl-x" onClick={() => setOpen(false)} aria-label="Close">✕</button>
            </div>
            {error ? (
              <div className="phl-err">{error}</div>
            ) : info ? (
              <>
                <div className="phl-qr" dangerouslySetInnerHTML={{ __html: info.qr_svg }} />
                <div className="phl-url">{info.url}</div>
              </>
            ) : (
              <div className="phl-status">Loading…</div>
            )}
            {!error && (
              <div className="phl-status">{received ? 'Photo received — asking your selves' : 'Waiting for a photo…'}</div>
            )}
            <div className="phl-hint">Phone and laptop on the same Wi-Fi. Scan, take a photo, look up.</div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}
