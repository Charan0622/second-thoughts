import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { AnimatePresence, MotionConfig, motion } from 'framer-motion'
import {
  fetchDemoItems, fetchHealth, fetchPersona, streamVerdict,
  type AgentId, type DemoItem, type DemoItemId, type NegotiationEvent, type PerceiveEvent, type Persona,
  type PoolEvent, type SentenceEvent, type VerdictEvent, type VerdictRequest, type VerdictStreamEvent,
  type VetoEvent, type VoteEvent,
} from './api'
import { MOCK_DEMO_ITEMS, MOCK_PERSONA, mockVerdict } from './mock'
import Camera from './Camera'
import Council, { Evidence } from './Council'
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
  error?: string
}

type Action = { kind: 'reset' } | { kind: 'clear' } | { kind: 'event'; ev: VerdictStreamEvent } | { kind: 'fail'; message?: string }

const initial: RunState = { runId: 0, phase: 'idle', votes: {} }

function reducer(s: RunState, a: Action): RunState {
  if (a.kind === 'reset') return { runId: s.runId + 1, phase: 'perceiving', votes: {} }
  if (a.kind === 'clear') return { runId: s.runId + 1, phase: 'idle', votes: {} }
  if (a.kind === 'fail') return { ...s, phase: s.verdict ? 'done' : 'error', error: a.message ?? s.error }
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
    case 'error': return { ...s, phase: s.verdict ? 'done' : 'error', error: ev.message }
    case 'agent_error': return s
    default: return s
  }
}

interface Toast { id: number; text: string }

const forceMock = new URLSearchParams(window.location.search).has('mock')
const DEMO_IDS: DemoItemId[] = ['shoes', 'headphones', 'macmini']

export default function App() {
  const [state, dispatch] = useReducer(reducer, initial)
  const [mock, setMock] = useState<boolean>(forceMock)
  const [items, setItems] = useState<DemoItem[]>(MOCK_DEMO_ITEMS)
  const [persona, setPersona] = useState<Persona | null>(null)
  const [demoMode, setDemoMode] = useState(true)
  const [selected, setSelected] = useState<DemoItemId>('headphones')
  const [manualPrice, setManualPrice] = useState('')
  const [muted, setMuted] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [ready, setReady] = useState(false)
  const [inspect, setInspect] = useState<AgentId | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const captureRef = useRef<(() => void) | null>(null)
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
    setInspect(null)
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
      const message = e instanceof Error ? e.message : String(e)
      dispatch({ kind: 'fail', message })
      toast(message)
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

  const busy = state.phase === 'perceiving' || state.phase === 'council' || state.phase === 'pooled'

  const ask = useCallback(() => {
    if (busy) return
    if (demoMode) runDemo(selected)
    else captureRef.current?.()
  }, [busy, demoMode, runDemo, selected])

  // Picking a different item returns to the quiet "desire" state until asked.
  const choose = useCallback((id: DemoItemId) => {
    if (id === selected && state.phase === 'idle') return
    abortRef.current?.abort()
    setSelected(id)
    setInspect(null)
    dispatch({ kind: 'clear' })
  }, [selected, state.phase])

  // Keyboard: 1/2/3 run a demo item, ←/→ cycle, Enter asks, Esc closes evidence.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (e.key === 'Escape') { setInspect(null); return }
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON' || e.metaKey || e.ctrlKey) return
      const idx = ['1', '2', '3'].indexOf(e.key)
      if (idx >= 0 && demoMode) { e.preventDefault(); runDemo(DEMO_IDS[idx]) }
      if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && demoMode) {
        const cur = DEMO_IDS.indexOf(selected)
        runDemo(DEMO_IDS[(cur + (e.key === 'ArrowRight' ? 1 : 2)) % 3])
      }
      if (e.key === 'Enter') { e.preventDefault(); ask() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [demoMode, runDemo, selected, ask])

  // ?run=shoes|headphones|macmini auto-starts a demo once live/mock is decided.
  const autoRan = useRef(false)
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('run') as DemoItemId | null
    if (!ready || autoRan.current || !id || !DEMO_IDS.includes(id)) return
    autoRan.current = true
    runDemo(id)
  }, [ready, runDemo])

  useEffect(() => {
    if (muted && 'speechSynthesis' in window) window.speechSynthesis.cancel()
  }, [muted])

  const stage = state.verdict ? 'resolved'
    : state.negotiation ? 'negotiating'
    : Object.keys(state.votes).length ? 'disagreeing'
    : state.phase === 'idle' || (state.phase === 'error' && !state.perceive) ? 'desire'
    : 'awakening'

  return (
    <MotionConfig reducedMotion="user">
      <div className={`app stage-${stage}`} data-band={state.verdict?.band ?? ''}>
        <header className="mast">
          <div className="brand">
            <span className="brand-mark" aria-hidden><i /><i /></span>
            <span className="brand-name">Second Thoughts</span>
            <span className="brand-tag">Your future selves weigh in before you pay.</span>
          </div>
          <PersonaLine persona={persona} />
          <span className={`source ${mock ? 'source-mock' : 'source-live'}`} title={mock ? 'Backend not reachable: replaying recorded fixture events' : 'Connected to the live backend'}>
            {mock ? 'Mock fixtures' : 'Live'}
          </span>
        </header>

        <main className="chamber">
          <Council state={state} side="left" agents={['budget', 'goals']} onInspect={setInspect} inspecting={inspect} />
          <Camera
            demoMode={demoMode}
            setDemoMode={setDemoMode}
            items={items}
            selected={selected}
            onSelect={choose}
            onAsk={ask}
            onCapture={runFrame}
            captureRef={captureRef}
            manualPrice={manualPrice}
            setManualPrice={setManualPrice}
            phase={state.phase}
            perceive={state.perceive}
            busy={busy}
            resolved={!!state.verdict}
          />
          <Council state={state} side="right" agents={['owned', 'deal']} onInspect={setInspect} inspecting={inspect} />
        </main>

        <Verdict state={state} muted={muted} setMuted={setMuted} mock={mock} onInspect={setInspect} />

        <Ledger mock={mock} />

        <AnimatePresence>
          {inspect && state.votes[inspect] && (
            <Evidence key={inspect} agent={inspect} state={state} mock={mock} onClose={() => setInspect(null)} />
          )}
        </AnimatePresence>

        <div className="toasts" role="status" aria-live="polite">
          <AnimatePresence>
            {toasts.map((t) => (
              <motion.div key={t.id} className="toast" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
                <strong>Error</strong> {t.text}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </MotionConfig>
  )
}

const usd = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`

function PersonaLine({ persona }: { persona: Persona | null }) {
  if (!persona) return <div className="persona persona-loading">Loading persona…</div>
  const pct = Math.min(1, persona.japan.saved / persona.japan.target)
  const payday = new Date(persona.next_payday + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return (
    <dl className="persona" aria-label={`${persona.name}'s situation`}>
      <div className="persona-who"><dt className="sr">Person</dt><dd>{persona.name}</dd></div>
      <div><dt>Free before payday</dt><dd>{usd(persona.free_cash)}</dd></div>
      <div><dt>Payday</dt><dd>{payday}</dd></div>
      <div className="persona-japan">
        <dt>Japan fund</dt>
        <dd>{usd(persona.japan.saved)}<span> / {usd(persona.japan.target)}</span></dd>
        <span className="meter" aria-hidden><span style={{ width: `${pct * 100}%` }} /></span>
      </div>
    </dl>
  )
}
