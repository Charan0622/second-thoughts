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
import Verdict, { Clarity } from './Verdict'
import Landing from './Landing'
import Ledger from './Ledger'
import PhoneLink from './PhoneLink'
import DocsPanel from './DocsPanel'

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
  const startParams = new URLSearchParams(window.location.search)
  const [view, setView] = useState<'landing' | 'app'>(startParams.has('run') || startParams.has('app') ? 'app' : 'landing')
  const [clarity, setClarity] = useState(false)
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
        let up = false
        for (let i = 0; i < 25 && !cancelled && !up; i++) {
          try { await fetchHealth(); up = true } catch { await new Promise((r) => setTimeout(r, 1000)) }
        }
        if (!up) { useMock = true; toast('Backend offline — showing MOCK data. Start the backend and reload.') }
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
    let timedOut = false
    const guard = setTimeout(() => { timedOut = true; ctl.abort() }, 30000)
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    setInspect(null)
    setClarity(false)
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
      if (timedOut) { toast('That took too long — try again or type the price'); dispatch({ kind: 'reset' }); return }
      if (ctl.signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return
      const message = e instanceof Error ? e.message : String(e)
      dispatch({ kind: 'fail', message })
      toast(message)
    } finally {
      clearTimeout(guard)
    }
  }, [mock, speak, toast])

  const parsedPrice = (() => {
    const n = parseFloat(manualPrice.replace(/[$,\s]/g, ''))
    return Number.isFinite(n) && n > 0 ? n : null
  })()

  const runDemo = useCallback((id: DemoItemId) => {
    setSelected(id)
    run({ demo_item: id, frame: null, price: null, item_name: null })
  }, [run])

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
    setClarity(false)
    dispatch({ kind: 'clear' })
  }, [selected, state.phase])

  // Keyboard: 1/2/3 run a demo item, ←/→ cycle, Enter asks, Esc closes evidence.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (e.key === 'Escape') { setInspect(null); setClarity(false); return }
      if (view !== 'app') return
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.metaKey || e.ctrlKey) return
      if (tag === 'BUTTON' && (e.key === 'Enter' || e.key === ' ')) return
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
  }, [demoMode, runDemo, selected, ask, view])

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

  // Act V: once the verdict exists, let the council's final positions register, then resolve the stage.
  // A timer, not an animation dependency: the verdict is already in state and in "How they decided".
  const verdictRun = state.verdict ? state.runId : null
  const negotiated = !!state.negotiation
  useEffect(() => {
    if (verdictRun == null) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const t = setTimeout(() => {
      setClarity(true)
      document.querySelector('.arena')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    }, reduce ? 0 : negotiated ? 1700 : 900)
    return () => clearTimeout(t)
  }, [verdictRun, negotiated])

  const stage = state.verdict ? 'resolved'
    : state.negotiation ? 'negotiating'
    : Object.keys(state.votes).length ? 'disagreeing'
    : state.phase === 'idle' || (state.phase === 'error' && !state.perceive) ? 'desire'
    : 'awakening'

  const item = items.find((i) => i.id === selected)

  if (view === 'landing') {
    return (
      <MotionConfig reducedMotion="user">
        <Landing item={item} mock={mock}
          onStart={() => setView('app')}
          onDemo={() => { setView('app'); runDemo(selected) }} />
      </MotionConfig>
    )
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className={`app stage-${stage}`} data-band={state.verdict?.band ?? ''}>
        <header className="mast">
          <button className="wordmark" onClick={() => { abortRef.current?.abort(); setView('landing'); dispatch({ kind: 'clear' }); setClarity(false) }} aria-label="Second Thoughts: back to start">
            <span className="brand-mark" aria-hidden><i /><i /></span>Second Thoughts
          </button>
          <PersonaLine persona={persona} />
          <DocsPanel onChange={() => { fetchPersona().then(setPersona).catch(() => {}) }} />
          <PhoneLink runId={state.runId} onFrame={(frame, price) => run({ demo_item: null, frame, price: price ?? parsedPrice, item_name: null })} />
          <span className={`source ${mock ? 'source-mock' : 'source-live'}`} title={mock ? 'Backend not reachable: replaying recorded fixture events' : 'Connected to the live backend'}>
            {mock ? 'Mock fixtures' : 'Live'}
          </span>
        </header>

        <main className="arena" data-act={stage}>
          <Council state={state} persona={persona} onInspect={setInspect} inspecting={inspect} />
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
          {state.negotiation && !state.verdict && (
            <motion.p className="act-note" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              Negotiating · {state.negotiation.chosen.label}
            </motion.p>
          )}
          <AnimatePresence>
            {clarity && state.verdict && (
              <Clarity key={state.runId} state={state} onBack={() => setClarity(false)} onAgain={() => { setClarity(false); choose(selected === 'shoes' ? 'headphones' : selected === 'headphones' ? 'macmini' : 'shoes') }} />
            )}
          </AnimatePresence>
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
