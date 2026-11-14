import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  fetchDemoItems, fetchHealth, fetchPersona, streamVerdict,
  type AgentId, type DemoItem, type DemoItemId, type NegotiationEvent, type PerceiveEvent, type Persona,
  type PoolEvent, type SentenceEvent, type VerdictEvent, type VerdictRequest, type VerdictStreamEvent,
  type VetoEvent, type VoteEvent,
} from './api'
import { MOCK_DEMO_ITEMS, MOCK_PERSONA, mockVerdict } from './mock'
import Camera from './Camera'
import Council from './Council'
import Gauge from './Gauge'
import Verdict from './Verdict'
import Ledger from './Ledger'

export type Phase = 'idle' | 'perceiving' | 'council' | 'pooled' | 'done' | 'error'

export interface RunState {
  runId: number
  phase: Phase
  perceive?: PerceiveEvent
  votes: Partial<Record<AgentId, VoteEvent>>
  veto?: VetoEvent
  pool?: PoolEvent
  negotiation?: NegotiationEvent
  verdict?: VerdictEvent
  sentence?: SentenceEvent
}

type Action = { kind: 'reset' } | { kind: 'event'; ev: VerdictStreamEvent } | { kind: 'fail' }

const initial: RunState = { runId: 0, phase: 'idle', votes: {} }

function reducer(s: RunState, a: Action): RunState {
  if (a.kind === 'reset') return { runId: s.runId + 1, phase: 'perceiving', votes: {} }
  if (a.kind === 'fail') return { ...s, phase: s.verdict ? 'done' : 'error' }
  const ev = a.ev
  switch (ev.type) {
    case 'perceive_start': return { ...s, phase: 'perceiving' }
    case 'perceive': return { ...s, perceive: ev }
    case 'council_start': return { ...s, phase: 'council' }
    case 'vote': return { ...s, votes: { ...s.votes, [ev.agent]: ev } }
    case 'veto': return { ...s, veto: ev }
    case 'pool': return { ...s, pool: ev, phase: 'pooled' }
    case 'negotiation': return { ...s, negotiation: ev }
    case 'verdict': return { ...s, verdict: ev, phase: 'done' }
    case 'sentence': return { ...s, sentence: ev }
    case 'done': return s.phase === 'done' ? s : { ...s, phase: 'done' }
    case 'error': return { ...s, phase: s.verdict ? 'done' : 'error' }
    case 'agent_error': return s
    default: return s
  }
}

interface Toast { id: number; text: string }

const forceMock = new URLSearchParams(window.location.search).has('mock')

export default function App() {
  const [state, dispatch] = useReducer(reducer, initial)
  const [mock, setMock] = useState<boolean>(forceMock)
  const [items, setItems] = useState<DemoItem[]>(MOCK_DEMO_ITEMS)
  const [persona, setPersona] = useState<Persona | null>(null)
  const [demoMode, setDemoMode] = useState(true)
  const [selected, setSelected] = useState<DemoItemId>('shoes')
  const [manualPrice, setManualPrice] = useState('')
  const [muted, setMuted] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [ready, setReady] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const mutedRef = useRef(muted)
  mutedRef.current = muted

  const toast = useCallback((text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000)
  }, [])

  // Decide live vs mock once, then load demo items + persona.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      let useMock = forceMock
      if (!useMock) {
        try { await fetchHealth() } catch { useMock = true }
      }
      if (cancelled) return
      setMock(useMock)
      setReady(true)
      if (useMock) { setPersona(MOCK_PERSONA); return }
      fetchDemoItems().then((d) => { if (!cancelled && d.length) setItems(d) }).catch(() => toast('Could not load demo items — using local frames'))
      fetchPersona().then((p) => { if (!cancelled) setPersona(p) }).catch(() => { if (!cancelled) setPersona(MOCK_PERSONA) })
    })()
    return () => { cancelled = true }
  }, [toast])

  const speak = useCallback((text: string) => {
    if (mutedRef.current || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    u.rate = 1.02
    window.speechSynthesis.speak(u)
  }, [])

  const run = useCallback(async (req: VerdictRequest) => {
    abortRef.current?.abort()
    const ctl = new AbortController()
    abortRef.current = ctl
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    dispatch({ kind: 'reset' })
    try {
      const stream = mock ? mockVerdict(req, ctl.signal) : streamVerdict(req, ctl.signal)
      for await (const ev of stream) {
        if (ctl.signal.aborted) return
        dispatch({ kind: 'event', ev })
        if (ev.type === 'error' || ev.type === 'agent_error') toast(ev.message)
        if (ev.type === 'sentence') speak(ev.text)
      }
    } catch (e) {
      if (ctl.signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return
      dispatch({ kind: 'fail' })
      toast(e instanceof Error ? e.message : String(e))
    }
  }, [mock, speak, toast])

  const parsedPrice = (() => {
    const n = parseFloat(manualPrice.replace(/[$,\s]/g, ''))
    return Number.isFinite(n) && n > 0 ? n : null
  })()

  const runDemo = useCallback((id: DemoItemId) => {
    setSelected(id)
    run({ demo_item: id, frame: null, price: parsedPrice, item_name: null })
  }, [run, parsedPrice])

  const runFrame = useCallback((frame: string) => {
    run({ demo_item: null, frame, price: parsedPrice, item_name: null })
  }, [run, parsedPrice])

  // Keyboard: 1/2/3 pick a demo item.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.metaKey || e.ctrlKey) return
      const ids: DemoItemId[] = ['shoes', 'headphones', 'macmini']
      const idx = ['1', '2', '3'].indexOf(e.key)
      if (idx >= 0 && demoMode) { e.preventDefault(); runDemo(ids[idx]) }
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        if (!demoMode) return
        const cur = ids.indexOf(selected)
        const next = ids[(cur + (e.key === 'ArrowRight' ? 1 : 2)) % 3]
        runDemo(next)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [demoMode, runDemo, selected])

  // ?run=shoes|headphones|macmini auto-starts a demo once live/mock is decided.
  const autoRan = useRef(false)
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('run') as DemoItemId | null
    if (!ready || autoRan.current || !id || !['shoes', 'headphones', 'macmini'].includes(id)) return
    autoRan.current = true
    runDemo(id)
  }, [ready, runDemo])

  useEffect(() => {
    if (muted && 'speechSynthesis' in window) window.speechSynthesis.cancel()
  }, [muted])

  const busy = state.phase === 'perceiving' || state.phase === 'council' || state.phase === 'pooled'

  return (
    <div className="stage">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>◐</span>
          <span className="brand-name">Second Thoughts</span>
          {mock && <span className="badge badge-mock" title="Backend not reachable — simulated events">MOCK</span>}
        </div>
        <PersonaStrip persona={persona} />
      </header>

      <main className="main">
        <section className="left">
          <Camera
            demoMode={demoMode}
            setDemoMode={setDemoMode}
            items={items}
            selected={selected}
            onPickDemo={runDemo}
            onCapture={runFrame}
            manualPrice={manualPrice}
            setManualPrice={setManualPrice}
            phase={state.phase}
            perceive={state.perceive}
            busy={busy}
          />
          <Ledger mock={mock} />
        </section>

        <section className="right">
          <Council state={state} />
          <Gauge state={state} />
          <Verdict state={state} muted={muted} setMuted={setMuted} mock={mock} />
        </section>
      </main>

      <div className="toasts" role="status" aria-live="polite">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div key={t.id} className="toast" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}>
              <strong>Error</strong> {t.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

const usd = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`

function PersonaStrip({ persona }: { persona: Persona | null }) {
  if (!persona) return <div className="persona persona-loading">Loading persona…</div>
  const pct = Math.min(1, persona.japan.saved / persona.japan.target)
  const payday = new Date(persona.next_payday + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return (
    <div className="persona">
      <span className="persona-name">{persona.name}</span>
      <span className="persona-sep" aria-hidden>·</span>
      <span className="persona-item"><span className="muted">free cash before payday</span> <b>{usd(persona.free_cash)}</b></span>
      <span className="persona-sep" aria-hidden>·</span>
      <span className="persona-item"><span className="muted">payday</span> <b>{payday}</b></span>
      <span className="persona-sep" aria-hidden>·</span>
      <span className="persona-item persona-japan">
        <span className="muted">Japan fund</span> <b>{usd(persona.japan.saved)}</b><span className="muted"> / {usd(persona.japan.target)}</span>
        <span className="meter" aria-hidden><span className="meter-fill" style={{ width: `${pct * 100}%` }} /></span>
      </span>
    </div>
  )
}
