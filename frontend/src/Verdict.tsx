import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AGENTS, fetchExplain, type AgentId, type Band, type NegotiationEvent } from './api'
import type { RunState } from './App'
import { AGENT_META, positionOf } from './Council'
import Gauge from './Gauge'


/** The words the stage resolves into. The backend's own title is shown beneath. */
export const CLARITY: Record<Band, { big: string; small?: string }> = {
  buy: { big: 'Buy it.' },
  buy_with_condition: { big: 'Yes.', small: 'With a condition.' },
  wait: { big: 'Not yet.' },
}

/* ---------- Act V · Clarity: the verdict takes over the stage ---------- */

export function Clarity({ state, onBack, onAgain }: { state: RunState; onBack: () => void; onAgain: () => void }) {
  const v = state.verdict!
  const c = CLARITY[v.band]
  const moved = AGENTS.filter((a) => positionOf(state, a).moved)
  const price = v.item?.price ?? state.perceive?.price ?? null
  const name = v.item?.name ?? state.perceive?.item_name
  return (
    <section className={`clarity band-${v.band}`} aria-label="The verdict" aria-live="assertive">
      <div className="clarity-inner">
        <p className="clarity-eyebrow">
          {name}{price != null ? ` · $${price.toLocaleString('en-US')}` : ''} · decided in {((v.council_ms ?? v.total_ms) / 1000).toFixed(2)} s
        </p>
        <h2 className="clarity-word rise" style={{ animationDelay: '100ms' }}>
          {c.big}{c.small && <em> {c.small}</em>}
        </h2>
        {v.condition && (
          <p className="clarity-condition enter" style={{ animationDelay: '350ms' }}>{v.condition}</p>
        )}

        <dl className="clarity-facts enter" style={{ animationDelay: '550ms' }}>
          <div><dd>{v.price_terms.hours_of_work.toFixed(1)}<small>h</small></dd><dt>of take-home pay</dt></div>
          <div><dd>{v.price_terms.japan_slip_days}<small>d</small></dd><dt>{v.price_terms.goal_name ?? 'Japan'} slips</dt></div>
          <div><dd>{v.price_terms.pct_free_cash}<small>%</small></dd><dt>of free cash before payday</dt></div>
        </dl>

        <p className="clarity-why enter" style={{ animationDelay: '750ms' }}>
          {state.sentence ? <>“{state.sentence.text}”<span>{state.sentence.source === 'deepinfra' ? 'DeepInfra' : 'template'}</span></>
            : <>Council: {v.title} · first vote {v.tally.buy} buy, {v.tally.wait} wait{moved.length ? ` · ${moved.map((a) => AGENT_META[a].label).join(' and ')} moved` : ''}</>}
        </p>

        <div className="clarity-actions">
          <button className="cta-quiet on-dark" onClick={onBack}>See how they decided</button>
          <button className="cta-quiet on-dark" onClick={onAgain}>Ask about something else</button>
        </div>
      </div>
    </section>
  )
}

/* ---------- How they decided: split, scale, negotiation, the Clerk ---------- */

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
      const text = mock ? await new Promise<string>((r) => setTimeout(() => r(MOCK_CLERK), 2500)) : await fetchExplain(ctl.signal)
      if (!ctl.signal.aborted) setClerk({ state: 'done', text })
    } catch (e) {
      if (!ctl.signal.aborted) setClerk({ state: 'error', text: e instanceof Error ? e.message : String(e) })
    }
  }

  const busy = state.phase === 'perceiving' || state.phase === 'council' || state.phase === 'pooled'
  const voted = AGENTS.filter((a) => state.votes[a])
  const buyers = voted.filter((a) => state.votes[a]!.stance === 'buy')
  const waiters = voted.filter((a) => state.votes[a]!.stance === 'wait')

  if (!voted.length && state.phase !== 'error') return null

  return (
    <section className="decided" aria-label="How they decided">
      <div className="decided-inner">
        <header className="decided-head">
          <h2>{v ? 'How they decided' : busy ? 'Your selves are deciding' : 'The council'}</h2>
          {v && <p className="decided-title">Council verdict: <b>{v.title}</b>{v.condition ? ` · ${v.condition}` : ''}</p>}
          {state.phase === 'error' && <p className="decided-error">The council couldn’t finish: {state.error ?? 'try again.'}</p>}
        </header>

        {voted.length > 0 && (
          <div className="split">
            <p className="label">Round one</p>
            <p className="split-line">
              <span><b>{buyers.length}</b> buy {buyers.map((a) => <Name key={a} a={a} onInspect={onInspect} />)}</span>
              <span><b>{waiters.length}</b> wait {waiters.map((a) => <Name key={a} a={a} onInspect={onInspect} />)}</span>
            </p>
            <Gauge state={state} />
          </div>
        )}

        <AnimatePresence>{state.negotiation && <Negotiation n={state.negotiation} />}</AnimatePresence>

        {v && (
          <div className="decided-tools">
            {state.phase === 'done' && (
              <button className="cta-quiet" onClick={askClerk} disabled={clerk.state === 'loading'}>
                {clerk.state === 'loading' ? 'The Clerk is reading…' : 'Ask the Clerk why'} <small>Intern</small>
              </button>
            )}
            <button className="cta-quiet" onClick={() => setMuted(!muted)} aria-pressed={muted}>{muted ? 'Voice off' : 'Voice on'}</button>
          </div>
        )}

        <AnimatePresence>
          {(clerk.state === 'done' || clerk.state === 'error') && (
            <motion.aside className={`clerk ${clerk.state === 'error' ? 'is-error' : ''}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <p className="label">The Clerk explains · Intern{mock ? ' · simulated' : ''}</p>
              <p>{clerk.text}</p>
              <button className="cta-quiet" onClick={() => setClerk({ state: 'idle' })}>Close</button>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </section>
  )
}

function Name({ a, onInspect }: { a: AgentId; onInspect: (a: AgentId) => void }) {
  return (
    <button className="name" style={{ ['--a' as string]: `var(--${a})` }} onClick={() => onInspect(a)}>
      <span className={`mark mark-${a}`} aria-hidden />{AGENT_META[a].label}
    </button>
  )
}

function Negotiation({ n }: { n: NegotiationEvent }) {
  return (
    <div className="negotiation enter">
      <p className="label">The negotiation · {n.offers.length} compromises evaluated</p>
      <ol className="offers">
        {n.offers.map((o, i) => {
          const p = n.pooled_by_offer?.[o.id]
          const chosen = o.id === n.chosen.id
          return (
            <li key={o.id} className={`offer ${chosen ? 'is-chosen' : ''} enter`} style={{ animationDelay: `${50 * i}ms` }}>
              <span className="offer-label">{o.label}</span>
              {p != null ? (
                <span className="offer-p"><span className="offer-bar"><span style={{ width: `${p * 100}%` }} /></span>{p.toFixed(2)}</span>
              ) : <span className="offer-p muted">not scored</span>}
              {chosen && <span className="offer-chosen">Chosen</span>}
            </li>
          )
        })}
      </ol>
      {n.picks.length > 0 && (
        <p className="who-moved">
          {n.picks.map((p) => (
            <span key={p.agent} style={{ ['--a' as string]: `var(--${p.agent})` }}>
              <span className={`mark mark-${p.agent}`} aria-hidden />{AGENT_META[p.agent].label} <span className="num">{p.p_before.toFixed(2)} → {p.p_after.toFixed(2)}</span>
            </span>
          ))}
        </p>
      )}
    </div>
  )
}
