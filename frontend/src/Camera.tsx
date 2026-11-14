import { useEffect, useRef, useState, type MutableRefObject } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { DemoItem, DemoItemId, PerceiveEvent } from './api'
import type { Phase } from './App'

interface Props {
  demoMode: boolean
  setDemoMode: (v: boolean) => void
  items: DemoItem[]
  selected: DemoItemId
  onSelect: (id: DemoItemId) => void
  onAsk: () => void
  onCapture: (dataUrl: string) => void
  captureRef: MutableRefObject<(() => void) | null>
  manualPrice: string
  setManualPrice: (v: string) => void
  phase: Phase
  perceive?: PerceiveEvent
  busy: boolean
  resolved: boolean
}

const SHORT: Record<DemoItemId, string> = { shoes: 'Running shoes', headphones: 'Headphones', macmini: 'Mac mini' }
const SOURCE_LABEL: Record<PerceiveEvent['price_source'], string> = {
  ndi: 'Price read by NDI', manual: 'Price entered by you', cache: 'Cached price', bucket: 'Estimated price',
}

function grabFrame(video: HTMLVideoElement): string {
  const max = 1024
  const w = video.videoWidth, h = video.videoHeight
  const scale = Math.min(1, max / Math.max(w, h))
  const c = document.createElement('canvas')
  c.width = Math.round(w * scale)
  c.height = Math.round(h * scale)
  c.getContext('2d')!.drawImage(video, 0, 0, c.width, c.height)
  return c.toDataURL('image/jpeg', 0.85)
}

const money = (n: number) => {
  const whole = Number.isInteger(n)
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 })}`
}

export default function Camera(p: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [camError, setCamError] = useState<string | null>(null)
  const [still, setStill] = useState<string | null>(null)

  useEffect(() => {
    if (p.demoMode) return
    let stream: MediaStream | null = null
    let cancelled = false
    setCamError(null)
    navigator.mediaDevices?.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false })
      .then((s) => {
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return }
        stream = s
        if (videoRef.current) { videoRef.current.srcObject = s; void videoRef.current.play() }
      })
      .catch((e: unknown) => setCamError(e instanceof Error ? e.message : 'Camera unavailable'))
    return () => { cancelled = true; stream?.getTracks().forEach((t) => t.stop()) }
  }, [p.demoMode])

  const { captureRef, onCapture } = p
  useEffect(() => {
    captureRef.current = () => {
      const v = videoRef.current
      if (!v || !v.videoWidth) return
      const url = grabFrame(v)
      setStill(url)
      onCapture(url)
    }
  }, [captureRef, onCapture])

  const item = p.items.find((i) => i.id === p.selected)
  const scanning = p.phase === 'perceiving'
  const showStill = !p.demoMode && still && p.phase !== 'idle'

  // What we know about the item: the perceived reading once it lands, otherwise the demo item's tag.
  const name = p.perceive?.item_name ?? (p.demoMode ? item?.name : undefined)
  const price = p.perceive ? p.perceive.price : p.demoMode ? item?.price ?? null : null

  const label = p.busy ? 'Your selves are weighing in' : p.resolved ? 'Ask again' : p.demoMode ? 'Ask my selves' : 'Capture & ask my selves'

  return (
    <section className="desire" aria-label="The item you want">
      <div className="object">
        <div className={`frame-wrap ${scanning ? 'is-scanning' : ''}`}>
          {p.demoMode ? (
            item && <img key={item.id} className="frame" src={item.frame_url} alt={item.name} />
          ) : showStill ? (
            <img className="frame" src={still!} alt="Captured frame" />
          ) : camError ? (
            <div className="cam-error">Camera unavailable: {camError}. Switch back to the demo items.</div>
          ) : null}
          {!p.demoMode && <video ref={videoRef} className="frame" muted playsInline style={{ visibility: showStill ? 'hidden' : 'visible' }} />}
          <AnimatePresence>
            {scanning && (
              <motion.div className="scan" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <motion.span className="scan-line" animate={{ top: ['6%', '94%', '6%'] }} transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }} />
                <span className="scan-label">Reading the tag</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={`${name ?? 'none'}-${price ?? 'none'}`}
            className="tag"
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          >
            {name ? <h1 className="tag-name">{name}</h1> : <h1 className="tag-name tag-hint">Point the camera at a price tag</h1>}
            <div className="tag-price">{price != null ? money(price) : <span className="tag-unknown">Price unknown</span>}</div>
            <div className="tag-source">
              {p.perceive
                ? <>{SOURCE_LABEL[p.perceive.price_source] ?? p.perceive.price_source} · {p.perceive.category.replace(/_/g, ' ')} ({Math.round(p.perceive.category_p * 100)}%)</>
                : p.demoMode ? 'Demo item · price from its tag' : 'Live camera'}
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      <button className="ask" onClick={p.onAsk} disabled={p.busy || (!p.demoMode && !!camError)} aria-live="polite">
        <span className="ask-label">{label}</span>
        {p.busy ? <span className="ask-dots" aria-hidden><i /><i /><i /></span> : <span className="ask-key" aria-hidden>↵</span>}
      </button>

      <div className="pick">
        {p.demoMode ? (
          <div className="items" role="radiogroup" aria-label="Demo items">
            {p.items.map((it, i) => (
              <button
                key={it.id}
                role="radio"
                aria-checked={p.selected === it.id}
                className={`item ${p.selected === it.id ? 'is-on' : ''}`}
                onClick={() => p.onSelect(it.id)}
                disabled={p.busy}
              >
                <kbd>{i + 1}</kbd>{SHORT[it.id] ?? it.name}
              </button>
            ))}
          </div>
        ) : null}
        <div className="pick-row">
          <button className="link" onClick={() => { p.setDemoMode(!p.demoMode); setStill(null) }} disabled={p.busy}>
            {p.demoMode ? 'Use my camera' : 'Use demo items'}
          </button>
          <label className="override">
            <span>Price override</span>
            <input inputMode="decimal" placeholder="auto" value={p.manualPrice} onChange={(e) => p.setManualPrice(e.target.value)} />
          </label>
        </div>
      </div>
    </section>
  )
}
