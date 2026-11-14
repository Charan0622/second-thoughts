import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { AGENTS, type AgentId, type Citation, type Persona, type Pick, type VetoEvent, type VoteEvent } from './api'
import type { RunState } from './App'

export const AGENT_META: Record<AgentId, { label: string; short: string; question: string; reads: string }> = {
  budget: { label: 'Budget You', short: 'Budget', question: 'Can I afford it?', reads: 'bank statement and pay stub' },
  goals: { label: 'Goals You', short: 'Goals', question: 'What does it cost my future?', reads: 'savings tracker and rules memo' },
  owned: { label: 'Already-Own-It You', short: 'Already own it', question: 'Do I have one already?', reads: 'receipts' },
  deal: { label: 'Deal You', short: 'Deal', question: 'Is this the right price?', reads: 'live price search' },
}

const EASE = [0.16, 1, 0.3, 1] as const
type Stance = 'buy' | 'wait' | 'abstain'
const word = (s: Stance) => (s === 'buy' ? 'Buy' : s === 'abstain' ? 'Abstains' : 'Wait')
const stanceOf = (p: number): Stance => (p < 0.5 ? 'buy' : 'wait')
const amounts = (s: string) => [...s.matchAll(/\$\s?([\d,]+(?:\.\d+)?)/g)].map((m) => ({ text: `$${m[1]}`, n: parseFloat(m[1].replace(/,/g, '')) }))

/** Where each self sits, and where its line meets the object (viewBox 0–100). */
const ANCHOR: Record<AgentId, [number, number]> = { budget: [30, 26], goals: [30, 74], owned: [70, 26], deal: [70, 74] }
const CENTER: [number, number] = [50, 44]

export interface Position { first?: Stance; now?: Stance; moved: boolean; pick?: Pick }
export function positionOf(state: RunState, a: AgentId): Position {
  const vote = state.votes[a]
  const pick = state.negotiation?.picks.find((p) => p.agent === a)
  const first = vote ? (vote.stance ?? stanceOf(vote.p_regret)) : undefined
  const after = pick ? stanceOf(pick.p_after) : undefined
  const now = after ?? first
  return { first, now, moved: !!(first && after && first !== after), pick }
}

/** The Convergence Ring: how far apart the council is, from real numbers only.
 *  Votes so far → their average regret; pool → pooled regret; negotiation → the chosen offer's regret; veto → the veto's p. */
function convergence(state: RunState): { value: number; from?: number; label: string; zone: 'buy' | 'cond' | 'wait' } | null {
  const zone = (p: number) => (p < 0.35 ? 'buy' : p <= 0.65 ? 'cond' : 'wait') as 'buy' | 'cond' | 'wait'
  if (state.veto?.fired) return { value: state.veto.p, from: state.pool?.p, label: 'Budget veto ·', zone: 'wait' }
  if (state.negotiation) return { value: state.negotiation.chosen.p_after, from: state.pool?.p, label: 'After the compromise ·', zone: zone(state.negotiation.chosen.p_after) }
  if (state.pool) return { value: state.pool.p, label: 'Pooled', zone: zone(state.pool.p) }
  const ps = AGENTS.map((a) => state.votes[a]).filter((v): v is VoteEvent => !!v && v.stance !== 'abstain').map((v) => v.p_regret)
  if (!ps.length) return null
  const avg = ps.reduce((x, y) => x + y, 0) / ps.length
  return { value: avg, label: `Average of ${ps.length} vote${ps.length > 1 ? 's' : ''} ·`, zone: zone(avg) }
}

interface Props {
  state: RunState
  persona: Persona | null
  onInspect: (a: AgentId) => void
  inspecting: AgentId | null
}

export default function Council({ state, persona, onInspect, inspecting }: Props) {
  const awake = state.phase !== 'idle' && !(state.phase === 'error' && !state.perceive)
  const ring = convergence(state)
  return (
    <div className="council" aria-label="Your four selves">
      {ring && (
        <div className="ring-wrap" data-zone={ring.zone}>
          <span className="ring" style={{ ['--k' as string]: (0.5 + ring.value * 0.5).toFixed(3) }} aria-hidden />
          <p className="ring-label" aria-live="polite">
            <span>{ring.label}</span> regret{' '}
            {ring.from != null && <><b className="was">{ring.from.toFixed(2)}</b> → </>}
            <b>{ring.value.toFixed(2)}</b>
          </p>
        </div>
      )}
      {/* A line joins a self to the object only when that self says buy. */}
      <svg className="beams" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {AGENTS.map((a) => {
          const pos = positionOf(state, a)
          if (pos.now !== 'buy') return null
          const [x, y] = ANCHOR[a]
          const k = 0.55
          return (
            <line key={`${a}-${state.runId}-${pos.moved}`} className="beam" x1={x} y1={y} x2={x + (CENTER[0] - x) * k} y2={y + (CENTER[1] - y) * k}
              stroke={`var(--${a})`} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinecap="round"
              style={{ animationDelay: pos.moved ? '500ms' : '150ms' }} />
          )
        })}
      </svg>
      {AGENTS.map((a, i) => (
        <Self key={`${a}-${state.runId}`} agent={a} order={i} awake={awake} state={state} persona={persona}
          onInspect={() => onInspect(a)} inspecting={inspecting === a} />
      ))}
    </div>
  )
}

interface SelfProps {
  agent: AgentId
  order: number
  awake: boolean
  state: RunState
  persona: Persona | null
  onInspect: () => void
  inspecting: boolean
}

function Self({ agent, order, awake, state, persona, onInspect, inspecting }: SelfProps) {
  const meta = AGENT_META[agent]
  const vote = state.votes[agent]
  const { first, now, moved, pick } = positionOf(state, agent)
  const veto = agent === 'budget' ? state.veto : undefined
  const vetoed = !!veto?.fired
  const listening = awake && !vote && state.phase !== 'error'

  const content = (
    <>
      <span className="self-top">
        <span className={`mark mark-${agent}`} aria-hidden />
        <span className="self-name">{meta.label}</span>
      </span>

      {vote ? (
        <span className="self-stance enter" key={`${first}-${now}`}>
          {moved && <s className={`stance stance-${first} is-was`}>{word(first!)}</s>}
          <span className={`stance stance-${now}`}>{word(now!)}</span>
        </span>
      ) : (
        <span className={`self-question ${listening ? 'is-listening' : ''}`}>
          {listening ? <>Reading your {meta.reads}</> : meta.question}
        </span>
      )}

      {vote && (
        <span className="self-detail enter" style={{ animationDelay: '150ms' }}>
          <Viz agent={agent} vote={vote} state={state} persona={persona} />
          <span className="self-headline">{vote.headline}</span>
          {pick && moved && (
            <span className="self-moved">Moved by “{state.negotiation?.offers.find((o) => o.id === pick.offer_id)?.label ?? pick.offer_id}”</span>
          )}
          <span className="self-open">See the evidence</span>
        </span>
      )}

      {vetoed && <VetoStamp veto={veto!} />}
    </>
  )

  const cls = `self self-${agent} ${awake ? 'is-awake' : ''} ${vote ? 'has-vote' : ''} ${moved ? 'has-moved' : ''} ${vetoed ? 'is-veto' : ''} ${inspecting ? 'is-open' : ''}`
  const common = {
    className: `${cls} arrive`,
    'data-stance': now ?? 'none',
    style: { ['--a' as string]: `var(--${agent})`, ['--i' as string]: order, animationDelay: `${(awake ? 0 : 200) + order * 110}ms` },
  }
  return vote ? (
    <button type="button" {...common} onClick={onInspect} aria-label={`${meta.label} says ${word(now!)}. ${vote.headline}. Open the evidence.`}>
      {content}
    </button>
  ) : (
    <div {...common} aria-label={`${meta.label}: ${meta.question}`}>{content}</div>
  )
}

function VetoStamp({ veto }: { veto: VetoEvent }) {
  return (
    <span className="veto stamp" role="note"><b>Veto</b>{veto.reason}</span>
  )
}

/* Each self shows its fact in its own visual language. Every number is read from the stream. */
function Viz({ agent, vote, state, persona }: { agent: AgentId; vote: VoteEvent; state: RunState; persona: Persona | null }) {
  if (agent === 'budget') {
    const a = amounts(vote.headline)
    const big = a.at(-1)
    return big ? <span className="viz viz-budget"><span className="figure">{big.text}</span></span> : null
  }
  if (agent === 'goals') {
    const slip = state.verdict?.price_terms.japan_slip_days
    if (!persona) return null
    const pct = Math.min(1, persona.japan.saved / persona.japan.target)
    return (
      <span className="viz viz-goals" aria-label={`${persona.goal_short ?? 'Japan'} fund ${persona.japan.saved} of ${persona.japan.target}`}>
        <span className="timeline"><span className="timeline-fill" style={{ width: `${pct * 100}%` }} /><span className="timeline-dot" style={{ left: `${pct * 100}%` }} /></span>
        <span className="timeline-label">{persona.goal_short ?? 'Japan'} fund ${persona.japan.saved.toLocaleString('en-US')} / ${persona.japan.target.toLocaleString('en-US')}{slip != null ? <b> · slips {slip} days</b> : null}</span>
      </span>
    )
  }
  if (agent === 'owned') {
    return <span className="viz viz-owned"><span className="receipt">{vote.citation.quote.replace(/^[“"]|[”"]$/g, '')}</span></span>
  }
  const price = state.perceive?.price ?? null
  const other = amounts(vote.headline).find((x) => price == null || Math.abs(x.n - price) > 0.5)
  if (price == null || !other) return null
  const max = Math.max(price, other.n)
  return (
    <span className="viz viz-deal" aria-label={`This tag ${price}, elsewhere ${other.text}`}>
      <span className="bar"><span style={{ width: `${(price / max) * 100}%` }} /><em>this tag ${price.toLocaleString('en-US')}</em></span>
      <span className="bar bar-other"><span style={{ width: `${(other.n / max) * 100}%` }} /><em>elsewhere {other.text}</em></span>
    </span>
  )
}

/* ---------- Evidence trail ---------- */

export function Evidence({ agent, state, mock, onClose }: { agent: AgentId; state: RunState; mock: boolean; onClose: () => void }) {
  const vote = state.votes[agent]!
  const meta = AGENT_META[agent]
  const { first, now, moved, pick } = positionOf(state, agent)
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { closeRef.current?.focus() }, [])
  const cached = /cache/i.test(vote.citation.doc_label) || /cache/i.test(vote.citation.doc)
  const provenance = mock ? { tag: 'Simulated', text: 'Recorded fixture event, not a live model call' }
    : cached ? { tag: 'Cached', text: 'From a stored snapshot of a live source' }
    : { tag: 'Live', text: vote.citation.doc.startsWith('keenable') ? 'Live web search via Keenable' : 'Extracted from your documents by NDI' }
  const terms = state.verdict?.price_terms
  const calc = agent === 'budget' && terms ? `${terms.pct_free_cash}% of your free cash · ${terms.hours_of_work.toFixed(1)} hours of take-home pay`
    : agent === 'goals' && terms ? (terms.japan_slip_days > 0 ? `Pushes the ${terms.goal_name ?? 'Japan'} goal back ${terms.japan_slip_days} days` : `Paid from free cash — ${terms.goal_name ?? 'Japan'} stays on track (${terms.japan_slip_if_from_savings ?? 0} days if paid from savings)`)
    : null

  return (
    <motion.div className="sheet-scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.aside className="sheet" role="dialog" aria-modal="true" aria-label={`${meta.label}: evidence`}
        style={{ ['--a' as string]: `var(--${agent})` }} onClick={(e) => e.stopPropagation()}
        initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 24, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }}>
        <header className="sheet-head">
          <span className={`mark mark-${agent}`} aria-hidden />
          <span className="sheet-name">{meta.label}</span>
          <span className={`prov prov-${provenance.tag.toLowerCase()}`}>{provenance.tag}</span>
          <button ref={closeRef} className="sheet-close" onClick={onClose}>Close</button>
        </header>

        <p className="sheet-stance">
          {moved && <s className={`stance stance-${first}`}>{word(first!)}</s>} <span className={`stance stance-${now}`}>{word(now!)}</span>
        </p>
        <p className="sheet-headline">{vote.headline}</p>

        <ol className="trail">
          <li>
            <p className="label">The fact</p>
            <Source c={vote.citation} />
          </li>
          <li>
            <p className="label">Where it came from</p>
            <p>{vote.citation.doc_label}{vote.citation.page != null ? `, page ${vote.citation.page}` : ''} <code>{vote.citation.doc}</code></p>
            <p className="muted">{provenance.text}</p>
          </li>
          <li>
            <p className="label">Why it matters here</p>
            <p>{meta.question} {vote.headline}.</p>
            {calc && <p className="muted">Computed by the backend: {calc}</p>}
          </li>
          {pick && (
            <li>
              <p className="label">In the negotiation</p>
              <p>Re-asked with “{state.negotiation?.offers.find((o) => o.id === pick.offer_id)?.label ?? pick.offer_id}”: regret {pick.p_before.toFixed(2)} → <b>{pick.p_after.toFixed(2)}</b>.</p>
            </li>
          )}
          <li>
            <p className="label">The model</p>
            <p className="mono">{vote.model} · {vote.ms} ms · regret {vote.p_regret.toFixed(2)} · stake {vote.stake.toFixed(1)}/10{vote.cite_p != null ? ` · fact probability ${vote.cite_p.toFixed(2)}` : ''}</p>
          </li>
        </ol>
      </motion.aside>
    </motion.div>
  )
}

function Source({ c }: { c: Citation }) {
  const [failed, setFailed] = useState(false)
  if (c.crop_url && !failed) {
    return (
      <figure className="excerpt excerpt-img">
        <img src={c.crop_url} alt={`Excerpt from ${c.doc_label}: ${c.quote}`} onError={() => setFailed(true)} />
        <figcaption>{c.quote}</figcaption>
      </figure>
    )
  }
  return <blockquote className="excerpt"><p>{c.quote}</p></blockquote>
}
