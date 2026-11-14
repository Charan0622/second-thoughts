import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { fetchExplain, type Band } from './api'
import type { RunState } from './App'

const ICON: Record<Band, string> = { buy: '✓', buy_with_condition: '◐', wait: '✕' }

interface Props { state: RunState; muted: boolean; setMuted: (v: boolean) => void; mock: boolean }

const MOCK_CLERK = 'The council split two-two in round one: Budget You and Deal You were comfortable, but Goals You flagged your own rule — no gadgets over $200 before Japan — and Already-Own-It You found the $179 Pulse Pro earbuds you bought in March. The deciding move was the trade-off: resell those earbuds and put $149 into the Japan fund. With that, both dissenters dropped to under 5% regret, so the pooled verdict flipped from Wait to Buy with a condition.'

type Clerk = { state: 'idle' } | { state: 'loading' } | { state: 'done'; text: string } | { state: 'error'; text: string }

export default function Verdict({ state, muted, setMuted, mock }: Props) {
  const v = state.verdict
  const [clerk, setClerk] = useState<Clerk>({ state: 'idle' })
  const clerkAbort = useRef<AbortController | null>(null)

  // New run → drop any previous explanation.
  useEffect(() => {
    clerkAbort.current?.abort()
    setClerk({ state: 'idle' })
  }, [state.runId])

  const askClerk = async () => {
    clerkAbort.current?.abort()
    const ctl = new AbortController()
    clerkAbort.current = ctl
    setClerk({ state: 'loading' })
    try {
      const text = mock
        ? await new Promise<string>((r) => setTimeout(() => r(MOCK_CLERK), 2500))
        : await fetchExplain(ctl.signal)
      if (!ctl.signal.aborted) setClerk({ state: 'done', text })
    } catch (e) {
      if (!ctl.signal.aborted) setClerk({ state: 'error', text: e instanceof Error ? e.message : String(e) })
    }
  }

  const busy = state.phase === 'perceiving' || state.phase === 'council' || state.phase === 'pooled'
  return (
    <div className={`panel verdict ${v ? `verdict-${v.band}` : ''}`}>
      <button className="mute" onClick={() => setMuted(!muted)} aria-pressed={muted} title={muted ? 'Unmute voice' : 'Mute voice'}>
        {muted ? '🔇' : '🔊'}
      </button>
      <AnimatePresence mode="wait">
        {v ? (
          <motion.div
            key={`v-${state.runId}`}
            className="verdict-inner"
            initial={{ scale: 1.25, opacity: 0, y: -12 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 520, damping: 26 }}
          >
            <div className="verdict-top">
              <span className="verdict-icon" aria-hidden>{ICON[v.band]}</span>
              <h1 className="verdict-title">{v.title}</h1>
              <span className="verdict-time" title={`total incl. price read ${(v.total_ms / 1000).toFixed(2)} s`}>
                decided in <b>{((v.council_ms ?? v.total_ms) / 1000).toFixed(2)} s</b>
              </span>
            </div>
            <div className="verdict-mid">
              {v.condition && <span className="verdict-condition">{v.condition}</span>}
              <span className="tally">first vote: <b>{v.tally.buy}</b> buy · <b>{v.tally.wait}</b> wait</span>
              <span className="terms">
                <span className="chip term"><b>{v.price_terms.hours_of_work.toFixed(1)} h</b> of work</span>
                <span className="chip term">Japan slips <b>{v.price_terms.japan_slip_days} days</b></span>
                <span className="chip term"><b>{v.price_terms.pct_free_cash}%</b> of free cash</span>
              </span>
            </div>
            <div className="verdict-bottom">
              <AnimatePresence>
                {state.sentence && (
                  <motion.p className="sentence" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                    “{state.sentence.text}”
                    {state.sentence.source === 'template' && <span className="meta"> · template</span>}
                  </motion.p>
                )}
              </AnimatePresence>
              {state.phase === 'done' && (
                <button className="btn clerk-btn" onClick={askClerk} disabled={clerk.state === 'loading'}>
                  {clerk.state === 'loading' ? <><span className="spinner" aria-hidden /> Clerk is reading…</> : 'Ask the Clerk'}
                  <span className="clerk-tag">Intern · Clerk</span>
                </button>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.div key="placeholder" className="verdict-placeholder" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {state.phase === 'error'
              ? 'Something went wrong — try again.'
              : busy ? 'Your future selves are deliberating…' : 'Ask your future selves before you pay.'}
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {(clerk.state === 'done' || clerk.state === 'error') && (
          <motion.aside
            className={`clerk-pop ${clerk.state === 'error' ? 'clerk-error' : ''}`}
            initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
          >
            <div className="clerk-head">
              <span className="panel-title">The Clerk explains</span>
              <span className="clerk-tag">Intern · Clerk</span>
              <button className="clerk-close" onClick={() => setClerk({ state: 'idle' })} aria-label="Close">✕</button>
            </div>
            <p>{clerk.text}</p>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  )
}
