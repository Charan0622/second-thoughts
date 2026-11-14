import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AGENTS, fetchExplain, type AgentId, type Band, type NegotiationEvent } from './api'
import type { RunState } from './App'
import { AGENT_META } from './Council'
import Gauge from './Gauge'

const MARK: Record<Band, string> = { buy: '✓', buy_with_condition: '◐', wait: '✕' }
const EASE = [0.16, 1, 0.3, 1] as const

interface Props { state: RunState; muted: boolean; setMuted: (v: boolean) => void; mock: boolean; onInspect: (a: AgentId) => void }

const MOCK_CLERK = 'The council split two-two in round one: Budget You and Deal You were comfortable, but Goals You flagged your own rule — no gadgets over $200 before Japan — and Already-Own-It You found the $179 Pulse Pro earbuds you bought in March. The deciding move was the trade-off: resell those earbuds and put $149 into the Japan fund. With that, both dissenters dropped to under 5% regret, so the pooled verdict flipped from Wait to Buy with a condition.'

type Clerk = { state: 'idle' } | { state: 'loading' } | { state: 'done'; text: string } | { state: 'error'; text: string }

export default function Verdict({ state, muted, setMuted, mock, onInspect }: Props) {
  const v = state.verdict
  const [clerk, setClerk] = useState<Clerk>({ state: 'idle' })
  const clerkAbort = useRef<AbortController | null>(null)

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

  // When the verdict lands, bring it into view (it is the answer the person came for).
  const sectionRef = useRef<HTMLElement>(null)
  const runWithVerdict = v ? state.runId : null
  useEffect(() => {
    if (runWithVerdict == null) return
    const el = sectionRef.current
    if (!el) return
    const t = setTimeout(() => {
      const top = el.getBoundingClientRect().top
      if (top > window.innerHeight * 0.55) {
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
        window.scrollTo({ top: window.scrollY + top - 16, behavior: reduce ? 'auto' : 'smooth' })
      }
    }, 650)
    return () => clearTimeout(t)
  }, [runWithVerdict])

  const busy = state.phase === 'perceiving' || state.phase === 'council' || state.phase === 'pooled'
  const voted = AGENTS.filter((a) => state.votes[a])
  const buyers = voted.filter((a) => state.votes[a]!.stance === 'buy')
  const waiters = voted.filter((a) => state.votes[a]!.stance === 'wait')

  return (
    <section ref={sectionRef} className={`resolution ${v ? `is-resolved band-${v.band}` : ''}`} aria-label="The verdict" aria-live="polite">
      <div className="resolution-inner">
        {/* 03 · Disagreement: who is on which side, as soon as votes land */}
        {voted.length > 0 && (
          <div className="split">
            <p className="label">{state.phase === 'council' ? 'The selves are voting' : 'Round one'}</p>
            <p className="split-line">
              <span className="split-side"><b>{buyers.length}</b> buy {buyers.length > 0 && <Names ids={buyers} />}</span>
              <span className="split-vs" aria-hidden>·</span>
              <span className="split-side"><b>{waiters.length}</b> wait {waiters.length > 0 && <Names ids={waiters} />}</span>
            </p>
            <Gauge state={state} />
          </div>
        )}

        {/* 04 · Negotiation: only what the backend actually evaluated */}
        <AnimatePresence>
          {state.negotiation && <Negotiation n={state.negotiation} />}
        </AnimatePresence>

        {/* 05 · Verdict: never gated on an exit animation */}
        {v ? (
            <motion.div key={`v-${state.runId}`} className="verdict" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
              <div className="verdict-main">
                <p className="label">The verdict · decided in {((v.council_ms ?? v.total_ms) / 1000).toFixed(2)} s</p>
                <motion.h2 className="verdict-title" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: EASE }}>
                  <span className="verdict-mark" aria-hidden>{MARK[v.band]}</span>{/[.!?]$/.test(v.title) ? v.title : `${v.title}.`}
                </motion.h2>
                {v.condition && (
                  <motion.p className="verdict-condition" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE, delay: 0.25 }}>
                    <span className="label">The condition</span>{v.condition}
                  </motion.p>
                )}
                <AnimatePresence>
                  {state.sentence && (
                    <motion.p className="sentence" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                      “{state.sentence.text}”
                      <span className="sentence-src">{state.sentence.source === 'deepinfra' ? 'Written by DeepInfra' : 'Template sentence'}</span>
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>

              <motion.dl className="terms" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE, delay: 0.35 }}>
                <p className="label">What it costs you</p>
                <div><dt>hours of work</dt><dd>{v.price_terms.hours_of_work.toFixed(1)}</dd></div>
                <div><dt>days Japan slips</dt><dd>{v.price_terms.japan_slip_days}</dd></div>
                <div><dt>of your free cash</dt><dd>{v.price_terms.pct_free_cash}<small>%</small></dd></div>
              </motion.dl>

              <div className="verdict-foot">
                <span className="inspect">
                  Inspect a self:
                  {voted.map((a) => (
                    <button key={a} className="chip" style={{ ['--a' as string]: `var(--${a})` }} onClick={() => onInspect(a)}>
                      <span aria-hidden>{AGENT_META[a].glyph}</span> {AGENT_META[a].label}
                    </button>
                  ))}
                </span>
                <span className="tools">
                  {state.phase === 'done' && (
                    <button className="ghost" onClick={askClerk} disabled={clerk.state === 'loading'}>
                      {clerk.state === 'loading' ? 'The Clerk is reading…' : 'Ask the Clerk why'} <small>Intern</small>
                    </button>
                  )}
                  <button className="ghost" onClick={() => setMuted(!muted)} aria-pressed={muted}>{muted ? 'Voice off' : 'Voice on'}</button>
                </span>
              </div>
            </motion.div>
          ) : (
            <p className="waiting">
              {state.phase === 'error'
                ? <>The council couldn’t finish. <span>{state.error ?? 'Try again.'}</span></>
                : busy ? (voted.length ? 'Weighing the votes…' : 'Your selves are reading your documents…')
                : 'Hold that thought. Ask your selves before you pay.'}
            </p>
          )}

        <AnimatePresence>
          {(clerk.state === 'done' || clerk.state === 'error') && (
            <motion.aside className={`clerk ${clerk.state === 'error' ? 'is-error' : ''}`} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
              <p className="label">The Clerk explains · Intern{mock ? ' · mock' : ''}</p>
              <p>{clerk.text}</p>
              <button className="ghost" onClick={() => setClerk({ state: 'idle' })}>Close</button>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </section>
  )
}

function Names({ ids }: { ids: AgentId[] }) {
  return (
    <span className="names">
      {ids.map((a) => <span key={a} className="name" style={{ ['--a' as string]: `var(--${a})` }}>{AGENT_META[a].label}</span>)}
    </span>
  )
}

function Negotiation({ n }: { n: NegotiationEvent }) {
  const scored = n.offers.map((o) => ({ ...o, p: n.pooled_by_offer?.[o.id] }))
  return (
    <motion.div className="negotiation" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.5, ease: EASE }}>
      <p className="label">The negotiation · {n.offers.length} compromises evaluated</p>
      <ol className="offers">
        {scored.map((o, i) => {
          const chosen = o.id === n.chosen.id
          return (
            <motion.li key={o.id} className={`offer ${chosen ? 'is-chosen' : ''}`}
              initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.4, ease: EASE, delay: 0.06 * i }}>
              <span className="offer-label">{o.label}</span>
              {o.p != null ? (
                <span className="offer-p" aria-label={`pooled regret ${o.p.toFixed(2)}`}>
                  <span className="offer-bar"><motion.span initial={{ width: 0 }} animate={{ width: `${o.p * 100}%` }} transition={{ duration: 0.6, ease: EASE, delay: 0.06 * i + 0.1 }} /></span>
                  {o.p.toFixed(2)}
                </span>
              ) : <span className="offer-p offer-na">not scored</span>}
              {chosen && <span className="offer-chosen">Chosen</span>}
            </motion.li>
          )
        })}
      </ol>
      {n.picks.length > 0 && (
        <p className="who-moved">
          {n.picks.map((p) => (
            <span key={p.agent} className="name" style={{ ['--a' as string]: `var(--${p.agent})` }}>
              {AGENT_META[p.agent].label} <span className="num">{p.p_before.toFixed(2)} → {p.p_after.toFixed(2)}</span>
            </span>
          ))}
        </p>
      )}
    </motion.div>
  )
}
