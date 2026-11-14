import { useEffect, useRef, useState } from 'react'
import type { SayEvent } from './api'
import { AGENT_META } from './Council'
import './Debate.css'

/** The live debate: each self's first-person line as its event lands, newest at the bottom. */
/** `docked` pins it to the bottom of the stage on desktop while the council is still talking. */
/** The council decides in under a second; the transcript is paced so people can follow the argument. */
export const DEBATE_STEP_MS = 650

export default function Debate({ lines: all, done = false }: { lines: SayEvent[]; docked?: boolean; done?: boolean }) {
  // A side drawer that never blocks the stage: open while the selves argue, folds into a pill after the verdict.
  const [collapsed, setCollapsed] = useState(false)
  const listRef = useRef<HTMLOListElement>(null)
  const [shown, setShown] = useState(0)
  useEffect(() => {
    if (shown >= all.length) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const t = setTimeout(() => setShown((n) => n + 1), reduce || shown === 0 ? 0 : DEBATE_STEP_MS)
    return () => clearTimeout(t)
  }, [shown, all.length])
  const lines = all.slice(0, shown)
  const finished = done && shown >= all.length
  useEffect(() => {
    if (!finished) return
    const t = setTimeout(() => setCollapsed(true), 2500)
    return () => clearTimeout(t)
  }, [finished])

  useEffect(() => {
    const el = listRef.current
    if (!el) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? 'auto' : 'smooth' })
  }, [lines.length])

  if (!lines.length) return null
  if (collapsed) {
    return (
      <button type="button" className="debate-pill" onClick={() => setCollapsed(false)} aria-label="Show the debate">
        💬 The debate · {all.length}
      </button>
    )
  }
  return (
    <section className="debate is-drawer" aria-label="The council's debate">
      <div className="debate-head">
        <p className="debate-title">The debate</p>
        <button type="button" className="debate-close" onClick={() => setCollapsed(true)} aria-label="Hide the debate">✕</button>
      </div>
      <ol ref={listRef} className="debate-lines" aria-live="polite">
          {lines.map((l, i) => {
            const mod = l.agent === 'council'
            const name = l.agent === 'council' ? 'The council' : AGENT_META[l.agent]?.label ?? l.agent
            return (
              <li
                key={i}
                className={`debate-line${mod ? ' is-mod' : ''} phase-${l.phase}`}
                style={mod ? undefined : { ['--a' as string]: `var(--${l.agent})` }}
              >
                <span className="debate-who">{name}</span>
                <span className="debate-text">
                  {l.text}
                  {l.quote && <q className="debate-quote">{l.quote.replace(/^[“"]|[”"]$/g, '')}</q>}
                </span>
              </li>
            )
          })}
      </ol>
    </section>
  )
}
