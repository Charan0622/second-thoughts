import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { AgentId, Citation, Pick, VetoEvent, VoteEvent } from './api'
import type { RunState } from './App'

export const AGENT_META: Record<AgentId, { label: string; glyph: string; question: string; reads: string }> = {
  budget: { label: 'Budget You', glyph: '$', question: 'What can I actually afford?', reads: 'Bank statement · pay stub' },
  goals: { label: 'Goals You', glyph: '↗', question: 'What does this do to my future?', reads: 'Savings tracker · rules memo' },
  owned: { label: 'Already-Own-It You', glyph: '≈', question: 'Do I already have something like it?', reads: 'Receipts' },
  deal: { label: 'Deal You', glyph: '%', question: 'Is this a good price right now?', reads: 'Live price search' },
}

const EASE = [0.16, 1, 0.3, 1] as const
const word = (s: 'buy' | 'wait') => (s === 'buy' ? 'Buy' : 'Wait')
const stanceOf = (p: number): 'buy' | 'wait' => (p < 0.5 ? 'buy' : 'wait')

interface Props {
  state: RunState
  side: 'left' | 'right'
  agents: AgentId[]
  onInspect: (a: AgentId) => void
  inspecting: AgentId | null
}

export default function Council({ state, side, agents, onInspect, inspecting }: Props) {
  const awake = state.phase !== 'idle' && !(state.phase === 'error' && !state.perceive)
  const neg = state.negotiation
  return (
    <section className={`selves selves-${side}`} aria-label={side === 'left' ? 'Budget and goals' : 'Possessions and price'}>
      {agents.map((a, i) => (
        <Self
          key={`${a}-${state.runId}`}
          agent={a}
          side={side}
          order={side === 'left' ? i : i + 2}
          awake={awake}
          listening={awake && !state.votes[a] && state.phase !== 'error'}
          vote={state.votes[a]}
          veto={a === 'budget' ? state.veto : undefined}
          pick={neg?.picks.find((p) => p.agent === a)}
          offerLabel={(id) => neg?.offers.find((o) => o.id === id)?.label ?? id}
          onInspect={() => onInspect(a)}
          inspecting={inspecting === a}
        />
      ))}
    </section>
  )
}

interface SelfProps {
  agent: AgentId
  side: 'left' | 'right'
  order: number
  awake: boolean
  listening: boolean
  vote?: VoteEvent
  veto?: VetoEvent
  pick?: Pick
  offerLabel: (id: string) => string
  onInspect: () => void
  inspecting: boolean
}

function Self({ agent, side, order, awake, listening, vote, veto, pick, offerLabel, onInspect, inspecting }: SelfProps) {
  const meta = AGENT_META[agent]
  const first = vote ? vote.stance ?? stanceOf(vote.p_regret) : undefined
  const after = pick ? stanceOf(pick.p_after) : undefined
  const now = after ?? first
  const moved = !!(first && after && first !== after)
  const vetoed = !!veto?.fired

  const body = (
    <>
      <span className="tether" aria-hidden data-stance={now ?? 'none'} />
      <header className="self-head">
        <span className="glyph" aria-hidden>{meta.glyph}</span>
        <span className="self-name">{vote?.label ?? meta.label}</span>
      </header>
      <p className="self-q">{meta.question}</p>

      <div className="position" aria-live="polite">
        {vote ? (
            <motion.div key={`${first}-${after ?? ''}`} className="position-inner"
              initial={{ opacity: 0, y: 10, scale: 1.04 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.5, ease: EASE }}>
              {moved ? (
                <>
                  <span className={`stance stance-${first} is-struck`}>{word(first!)}</span>
                  <span className={`stance stance-${after}`}>{word(after!)}</span>
                </>
              ) : (
                <span className={`stance stance-${now}`}>{word(now!)}</span>
              )}
            </motion.div>
          ) : listening ? (
            <span className="listening">Reading {meta.reads.toLowerCase()}</span>
          ) : (
            <span className="quiet">Reads {meta.reads.toLowerCase()}</span>
          )}
      </div>

      {vote && (
        <motion.div className="self-body" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, delay: 0.1 }}>
          <p className="headline">{vote.headline}</p>
          <p className="cite"><span className="cite-mark" aria-hidden>“</span>{vote.citation.quote.replace(/^[“"]|[”"]$/g, '')}<span className="cite-src"> {vote.citation.doc_label}{vote.citation.page != null ? `, p.${vote.citation.page}` : ''}</span></p>
          {pick && (
            <p className="moved">
              With “{offerLabel(pick.offer_id)}”: regret {pick.p_before.toFixed(2)} → <b>{pick.p_after.toFixed(2)}</b>
            </p>
          )}
          <p className="numbers">
            <span>regret <b>{vote.p_regret.toFixed(2)}</b></span>
            <span>stake <b>{vote.stake.toFixed(1)}</b></span>
            <span className="open">Evidence →</span>
          </p>
        </motion.div>
      )}

      <AnimatePresence>
        {vetoed && (
          <motion.div className="veto" role="note"
            initial={{ opacity: 0, scale: 1.3, rotate: -6 }} animate={{ opacity: 1, scale: 1, rotate: -3 }}
            transition={{ duration: 0.45, ease: EASE, delay: 0.1 }}>
            <span className="veto-word">Veto</span>
            <span className="veto-reason">{veto!.reason}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )

  const cls = `self self-${agent} side-${side} ${awake ? 'is-awake' : ''} ${vote ? 'has-vote' : ''} ${moved ? 'has-moved' : ''} ${vetoed ? 'is-veto' : ''} ${inspecting ? 'is-open' : ''}`
  const enter = { opacity: awake ? 1 : 0.55, x: 0 }
  return vote ? (
    <motion.button type="button" className={cls} style={{ ['--a' as string]: `var(--${agent})` }}
      onClick={onInspect} aria-label={`${meta.label}: ${word(now!)}. Open evidence.`}
      initial={{ opacity: 0.55, x: side === 'left' ? -8 : 8 }} animate={enter} transition={{ duration: 0.6, ease: EASE, delay: awake ? order * 0.08 : 0 }}>
      {body}
    </motion.button>
  ) : (
    <motion.div className={cls} style={{ ['--a' as string]: `var(--${agent})` }}
      initial={{ opacity: 0.55, x: side === 'left' ? -8 : 8 }} animate={enter} transition={{ duration: 0.6, ease: EASE, delay: awake ? order * 0.08 : 0 }}>
      {body}
    </motion.div>
  )
}

/* ---------- Evidence sheet ---------- */

export function Evidence({ agent, state, mock, onClose }: { agent: AgentId; state: RunState; mock: boolean; onClose: () => void }) {
  const vote = state.votes[agent]!
  const meta = AGENT_META[agent]
  const pick = state.negotiation?.picks.find((p) => p.agent === agent)
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { closeRef.current?.focus() }, [])
  const provenance = mock ? 'Mock fixture: recorded event, not a live model call'
    : vote.citation.doc.startsWith('keenable') ? 'Live web search via Keenable'
    : 'Extracted from your documents by NDI'

  return (
    <motion.div className="sheet-scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.aside
        className="sheet" role="dialog" aria-modal="true" aria-label={`${meta.label}: evidence`}
        style={{ ['--a' as string]: `var(--${agent})` }}
        onClick={(e) => e.stopPropagation()}
        initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }}
        transition={{ duration: 0.4, ease: EASE }}>
        <header className="sheet-head">
          <span className="glyph" aria-hidden>{meta.glyph}</span>
          <div>
            <p className="sheet-name">{meta.label}</p>
            <p className="sheet-q">{meta.question}</p>
          </div>
          <button ref={closeRef} className="sheet-close" onClick={onClose} aria-label="Close evidence">Close</button>
        </header>

        <p className={`sheet-stance stance-${vote.stance}`}>{word(vote.stance)}</p>
        <p className="sheet-headline">{vote.headline}</p>
        {pick && (
          <p className="sheet-moved">
            Re-asked with “{state.negotiation?.offers.find((o) => o.id === pick.offer_id)?.label ?? pick.offer_id}”:
            regret {pick.p_before.toFixed(2)} → <b>{pick.p_after.toFixed(2)}</b>, so {word(stanceOf(pick.p_after)).toLowerCase()}.
          </p>
        )}

        <p className="label">The decisive fact</p>
        <Source c={vote.citation} />

        <dl className="facts">
          <div><dt>Source</dt><dd>{vote.citation.doc_label}{vote.citation.page != null ? `, page ${vote.citation.page}` : ''}</dd></div>
          <div><dt>File</dt><dd><code>{vote.citation.doc}</code></dd></div>
          {vote.citation.bbox && <div><dt>Region</dt><dd>{vote.citation.bbox.map((n) => n.toFixed(2)).join(', ')}</dd></div>}
          {vote.cite_p != null && <div><dt>Drex’s probability for this fact</dt><dd>{vote.cite_p.toFixed(2)}</dd></div>}
          <div><dt>Regret · stake</dt><dd>{vote.p_regret.toFixed(2)} · {vote.stake.toFixed(1)} of 10</dd></div>
          <div><dt>Model · time</dt><dd>{vote.model} · {vote.ms} ms</dd></div>
          <div><dt>Data</dt><dd>{provenance}</dd></div>
        </dl>
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
