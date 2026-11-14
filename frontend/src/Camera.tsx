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
  /** Demo items are reachable (only for the demo persona / mock): a small "or try an example" link. */
  examples: boolean
  onError?: (message: string) => void
}

const SHORT: Record<DemoItemId, string> = { shoes: 'Running shoes', headphones: 'Headphones', macmini: 'Mac mini' }
const SOURCE_LABEL: Record<PerceiveEvent['price_source'], string> = {
  ndi: 'Price read by NDI', manual: 'Price entered by you', cache: 'Cached price', bucket: 'Estimated price', vision: 'Price read from the photo',
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

/** An uploaded photo → JPEG data URL, longest side ≤ 1280 px (same shape as a webcam capture). */
function downscaleFile(file: File, max = 1280): Promise<string> {
  return new Promise((resolve, reject) => {
    const src = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight))
      const c = document.createElement('canvas')
      c.width = Math.max(1, Math.round(img.naturalWidth * scale))
      c.height = Math.max(1, Math.round(img.naturalHeight * scale))
      c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height)
      URL.revokeObjectURL(src)
      resolve(c.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = () => { URL.revokeObjectURL(src); reject(new Error('This browser can’t read that image — try a JPEG or PNG')) }
    img.src = src
  })
}

const money = (n: number) => {
  const whole = Number.isInteger(n)
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 })}`
}

export default function Camera(p: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [camError, setCamError] = useState<string | null>(null)
  // Camera picker: lets an iPhone (macOS Continuity Camera) or any USB/virtual camera be the eye.
  const [cams, setCams] = useState<MediaDeviceInfo[]>([])
  const [camId, setCamId] = useState<string>(() => { try { return localStorage.getItem('st-cam') ?? '' } catch { return '' } })
  const [still, setStill] = useState<string | null>(null)

  useEffect(() => {
    if (p.demoMode) return
    let stream: MediaStream | null = null
    let cancelled = false
    setCamError(null)
    navigator.mediaDevices?.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, ...(camId ? { deviceId: { exact: camId } } : {}) }, audio: false })
      .then(async (s) => {
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return }
        stream = s
        try {
          const list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput')
          setCams(list)
          const iphone = list.find((d) => /iphone|continuity/i.test(d.label))
          if (!camId && iphone && iphone.deviceId !== s.getVideoTracks()[0]?.getSettings().deviceId) { setCamId(iphone.deviceId); return }
        } catch { /* labels unavailable */ }
        if (videoRef.current) { videoRef.current.srcObject = s; void videoRef.current.play() }
      })
      .catch((e: unknown) => {
        // A remembered camera (e.g. an iPhone that's no longer nearby) can't open: fall back to the default camera.
        if (camId) { try { localStorage.removeItem('st-cam') } catch { /* ignore */ } setCamId(''); return }
        setCamError(e instanceof Error ? e.message : 'Camera unavailable')
      })
    return () => { cancelled = true; stream?.getTracks().forEach((t) => t.stop()) }
  }, [p.demoMode, camId])

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

  const upload = async (file: File | undefined) => {
    if (!file || p.busy) return
    try {
      const url = await downscaleFile(file)
      if (p.demoMode) p.setDemoMode(false)
      setStill(url)
      onCapture(url)                      // same path as a webcam capture: POST {frame, price}
    } catch (e) {
      p.onError?.(e instanceof Error ? e.message : String(e))
    }
  }

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
            <div className="cam-error">Camera unavailable: {camError}. Upload a photo instead.</div>
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

        <div key={`${name ?? 'none'}-${price ?? 'none'}`} className="tag enter">
            {name ? <h1 className="tag-name">{name}</h1> : <h1 className="tag-name tag-hint">Upload a photo or point the camera at a price tag</h1>}
            <div className="tag-price">{price != null ? money(price) : <span className="tag-unknown">Price unknown</span>}</div>
            <div className="tag-source">
              {p.perceive
                ? <>{SOURCE_LABEL[p.perceive.price_source] ?? p.perceive.price_source} · {p.perceive.category.replace(/_/g, ' ')} ({Math.round(p.perceive.category_p * 100)}%)</>
                : p.demoMode ? 'Demo item · price from its tag' : 'Live camera'}
            </div>
          </div>
      </div>

      <button className="ask" onClick={p.onAsk} disabled={p.busy || (!p.demoMode && !!camError)} aria-live="polite">
        <span className="ask-label">{label}</span>
        {p.busy ? <span className="ask-dots" aria-hidden><i /><i /><i /></span> : <span className="ask-key" aria-hidden>↵</span>}
      </button>

      <div className="pick">
        <label className="item" style={{ cursor: p.busy ? 'default' : 'pointer', alignSelf: 'center', opacity: p.busy ? 0.45 : 1 }}>
          📷 Upload a photo of what you want to buy
          <input type="file" accept="image/*" hidden disabled={p.busy}
            onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = '' }} />
        </label>
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
        {!p.demoMode && cams.length > 1 && (
          <label className="override cam-pick">
            <span>Camera</span>
            <select value={camId} onChange={(e) => { setCamId(e.target.value); try { localStorage.setItem('st-cam', e.target.value) } catch { /* ignore */ } }}>
              <option value="">Default</option>
              {cams.map((c, i) => <option key={c.deviceId || i} value={c.deviceId}>{c.label || `Camera ${i + 1}`}</option>)}
            </select>
          </label>
        )}
        <div className="pick-row">
          {p.examples ? (
            <button className="link" onClick={() => { p.setDemoMode(!p.demoMode); setStill(null) }} disabled={p.busy}>
              {p.demoMode ? 'Use my camera' : 'or try an example'}
            </button>
          ) : <span />}
          <label className="override">
            <span>Price override</span>
            <input inputMode="decimal" placeholder="auto" value={p.manualPrice} onChange={(e) => p.setManualPrice(e.target.value)} />
          </label>
        </div>
      </div>
    </section>
  )
}
