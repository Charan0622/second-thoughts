import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { DemoItem, DemoItemId, PerceiveEvent } from './api'
import type { Phase } from './App'

interface Props {
  demoMode: boolean
  setDemoMode: (v: boolean) => void
  items: DemoItem[]
  selected: DemoItemId
  onPickDemo: (id: DemoItemId) => void
  onCapture: (dataUrl: string) => void
  manualPrice: string
  setManualPrice: (v: string) => void
  phase: Phase
  perceive?: PerceiveEvent
  busy: boolean
}

const SHORT: Record<DemoItemId, string> = { shoes: 'Shoes', headphones: 'Headphones', macmini: 'Mac mini' }
const SOURCE_LABEL: Record<PerceiveEvent['price_source'], string> = {
  ndi: 'read by NDI', manual: 'manual', cache: 'cached', bucket: 'estimated',
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

  const capture = () => {
    const v = videoRef.current
    if (!v || !v.videoWidth) return
    const url = grabFrame(v)
    setStill(url)
    p.onCapture(url)
  }

  const item = p.items.find((i) => i.id === p.selected)
  const scanning = p.phase === 'perceiving'
  const showStill = !p.demoMode && still && p.phase !== 'idle'

  return (
    <div className="panel camera">
      <div className="camera-head">
        <span className="panel-title">The item</span>
        <label className="toggle">
          <input type="checkbox" checked={p.demoMode} onChange={(e) => { p.setDemoMode(e.target.checked); setStill(null) }} />
          <span className="toggle-track"><span className="toggle-thumb" /></span>
          <span>Demo mode</span>
        </label>
      </div>

      <div className="viewport">
        {p.demoMode ? (
          item && <img key={item.id} className="frame" src={item.frame_url} alt={item.name} />
        ) : showStill ? (
          <img className="frame" src={still!} alt="Captured frame" />
        ) : camError ? (
          <div className="cam-error">Camera unavailable — {camError}. Switch on Demo mode.</div>
        ) : null}
        {!p.demoMode && <video ref={videoRef} className="frame" muted playsInline style={{ visibility: showStill ? 'hidden' : 'visible' }} />}

        <AnimatePresence>
          {scanning && (
            <motion.div className="scan" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <motion.div className="scan-line" animate={{ top: ['0%', '100%', '0%'] }} transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }} />
              <span className="scan-label">Perceiving…</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence mode="wait">
        {p.perceive ? (
          <motion.div key={p.perceive.item_name + p.perceive.price} className="item-readout" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="item-name">{p.perceive.item_name}</div>
            <div className="item-meta">
              <span className="item-price">{p.perceive.price != null ? `$${p.perceive.price.toLocaleString('en-US')}` : '—'}</span>
              <span className="tag">{SOURCE_LABEL[p.perceive.price_source] ?? p.perceive.price_source}</span>
              <span className="item-cat">{p.perceive.category} <span className="muted">· {Math.round(p.perceive.category_p * 100)}%</span></span>
            </div>
          </motion.div>
        ) : (
          <motion.div key="hint" className="item-readout item-hint" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {p.demoMode ? 'Pick an item — or press 1 · 2 · 3' : 'Point the camera at a price tag and capture'}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="controls">
        {p.demoMode ? (
          <div className="demo-buttons">
            {p.items.map((it, i) => (
              <button key={it.id} className={`btn demo-btn ${p.selected === it.id ? 'active' : ''}`} onClick={() => p.onPickDemo(it.id)}>
                <kbd>{i + 1}</kbd> {SHORT[it.id] ?? it.name}
              </button>
            ))}
          </div>
        ) : (
          <button className="btn btn-primary capture" onClick={capture} disabled={!!camError || p.busy}>Capture &amp; ask</button>
        )}
        <label className="price-input">
          <span className="muted">Price $</span>
          <input inputMode="decimal" placeholder="auto" value={p.manualPrice} onChange={(e) => p.setManualPrice(e.target.value)} aria-label="Manual price override" />
        </label>
      </div>
    </div>
  )
}
