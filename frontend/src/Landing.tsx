import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from 'react'
import type { AgentId, DemoItem } from './api'
import { AGENT_META } from './Council'
import './Landing.css'

interface Props {
  item?: DemoItem
  onStart: () => void
  onDemo?: () => void
  mock?: boolean
}

const SELVES: AgentId[] = ['budget', 'goals', 'owned', 'deal']
const LEAVE_MS = 1350
const CYCLE_MS = 2600

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** A stable barcode for the tag, derived from the item's name (decoration, not data). */
function bars(seed: string): number[] {
  let h = 2166136261
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  const out: number[] = []
  for (let i = 0; i < 34; i++) { h = Math.imul(h ^ (h >>> 13), 2246822507); out.push(1 + (Math.abs(h) % 3)) }
  return out
}

/**
 * The first viewport. The thing you want hangs on four threads; each thread is one of you.
 * Move and the nearest self wakes. Ask, and they come down their threads into the decision.
 */
export default function Landing({ item, onStart }: Props) {
  const [awake, setAwake] = useState(0)
  const [engaged, setEngaged] = useState(false)
  const [leaning, setLeaning] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [still] = useState(reduced)

  const rootRef = useRef<HTMLElement>(null)
  const tagRef = useRef<HTMLSpanElement>(null)
  const eyeRef = useRef<HTMLSpanElement>(null)
  const selfRefs = useRef<(HTMLLIElement | null)[]>([])
  const knotRefs = useRef<(HTMLSpanElement | null)[]>([])
  const pathRefs = useRef<(SVGPathElement | null)[]>([])
  const pointer = useRef({ x: 0, y: 0, on: false })
  const live = useRef({ awake: 0, taut: false })
  useEffect(() => { live.current = { awake, taut: leaning || leaving } }, [awake, leaning, leaving])

  // Idle: the council murmurs, one self at a time.
  useEffect(() => {
    if (still || engaged || leaving) return
    const t = setInterval(() => setAwake((a) => (a + 1) % 4), CYCLE_MS)
    return () => clearInterval(t)
  }, [still, engaged, leaving])

  // One loop draws the threads from each self's knot to the eyelet and lets the tag swing on it.
  useEffect(() => {
    let raf = 0
    const sag = [1, 1, 1, 1]
    const tilt = { x: 0, y: 0 }
    const t0 = performance.now()
    const tick = (now: number) => {
      const root = rootRef.current, eye = eyeRef.current, tag = tagRef.current
      if (root && eye && tag) {
        const p = pointer.current
        const sway = still ? 0 : Math.sin((now - t0) / 1900) * 0.35
        const tx = still ? 0 : p.on ? (p.x / window.innerWidth) * 2 - 1 : sway
        const ty = still ? 0 : p.on ? (p.y / window.innerHeight) * 2 - 1 : 0
        tilt.x += (tx - tilt.x) * 0.07
        tilt.y += (ty - tilt.y) * 0.07
        tag.style.setProperty('--tx', tilt.x.toFixed(4))
        tag.style.setProperty('--ty', tilt.y.toFixed(4))

        const rr = root.getBoundingClientRect()
        const e = eye.getBoundingClientRect()
        const ex = e.left + e.width / 2 - rr.left
        const ey = e.top + e.height / 2 - rr.top
        for (let i = 0; i < 4; i++) {
          const k = knotRefs.current[i], path = pathRefs.current[i]
          if (!k || !path) continue
          const r = k.getBoundingClientRect()
          const ax = r.left + r.width / 2 - rr.left
          const ay = r.top + r.height / 2 - rr.top
          const target = live.current.taut || live.current.awake === i ? 0 : 1
          sag[i] += (target - sag[i]) * (still ? 1 : 0.09)
          const len = Math.hypot(ex - ax, ey - ay)
          const mx = (ax + ex) / 2
          const my = (ay + ey) / 2 + sag[i] * Math.min(42, len * 0.12)
          path.setAttribute('d', `M${ax.toFixed(1)},${ay.toFixed(1)} Q${mx.toFixed(1)},${my.toFixed(1)} ${ex.toFixed(1)},${ey.toFixed(1)}`)
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [still])

  const nearest = (x: number, y: number) => {
    let best = 0, d = Infinity
    selfRefs.current.forEach((el, i) => {
      if (!el) return
      const r = el.getBoundingClientRect()
      const dd = Math.hypot(r.left + r.width / 2 - x, r.top + r.height / 2 - y)
      if (dd < d) { d = dd; best = i }
    })
    return best
  }

  const move = (e: PointerEvent) => {
    if (leaving) return
    pointer.current = { x: e.clientX, y: e.clientY, on: true }
    if (!engaged) setEngaged(true)
    const n = nearest(e.clientX, e.clientY)
    if (n !== awake) setAwake(n)
  }
  const leave = () => { pointer.current.on = false; setEngaged(false) }

  const ask = () => {
    if (leaving) return
    if (still) { onStart(); return }
    // Each self travels down its own thread: its knot ends exactly on the eyelet.
    const eye = eyeRef.current?.getBoundingClientRect()
    if (eye) {
      selfRefs.current.forEach((el, i) => {
        const k = knotRefs.current[i]
        if (!el || !k) return
        const r = k.getBoundingClientRect()
        el.style.setProperty('--cx', `${(eye.left + eye.width / 2 - (r.left + r.width / 2)).toFixed(1)}px`)
        el.style.setProperty('--cy', `${(eye.top + eye.height / 2 - (r.top + r.height / 2)).toFixed(1)}px`)
      })
    }
    pointer.current.on = false
    setLeaving(true)
    setTimeout(onStart, LEAVE_MS)
  }

  const price = item?.price ?? 0
  const whole = Math.floor(price).toLocaleString('en-US')
  const cents = Math.round((price % 1) * 100)

  return (
    <section
      ref={rootRef}
      className={`lp${leaving ? ' is-leaving' : ''}${leaning ? ' is-leaning' : ''}${still ? ' is-still' : ''}`}
      aria-label="Second Thoughts"
      onPointerMove={move}
      onPointerDown={move}
      onPointerLeave={leave}
    >
      <header className="lp-mast">
        <span className="lp-word"><span className="brand-mark" aria-hidden><i /><i /></span>Second Thoughts</span>
        <span className="lp-drex">Powered by <b>Drex</b></span>
      </header>

      <svg className="lp-threads" aria-hidden>
        {SELVES.map((a, i) => (
          <path key={a} ref={(el) => { pathRefs.current[i] = el }}
            className={`lp-thread${awake === i || leaning || leaving ? ' is-taut' : ''}`}
            style={{ ['--a' as string]: `var(--${a})` } as CSSProperties} />
        ))}
      </svg>


      <div className="lp-center">
        <h1 className="lp-h1">
          <span className="lp-a">You want</span>
          <span className="lp-tag-slot" aria-hidden>
            <span className="lp-tag" ref={tagRef}>
              <span className="lp-tag-face">
                <span className="lp-eyelet" ref={eyeRef} />
                {item && <span className="lp-tag-name">{item.name.replace(/-/g, '\u2011')}</span>}
                {item && (
                  <span className="lp-tag-price">
                    <sup>$</sup>{whole}{cents ? <sup>{String(cents).padStart(2, '0')}</sup> : null}
                  </span>
                )}
                <span className="lp-tag-code">
                  {bars(item?.name ?? 'second-thoughts').map((w, i) => <i key={i} style={{ width: w, marginRight: ((i * 7) % 3) + 1 }} />)}
                </span>
              </span>
            </span>
          </span>
          <span className="lp-b">it.</span>
        </h1>

        <ol className="lp-selves" aria-label="Four of you weigh in">
          {SELVES.map((a, i) => (
            <li key={a} ref={(el) => { selfRefs.current[i] = el }}
              className={`lp-self lp-self-${a}${still || awake === i || leaning || leaving ? ' is-awake' : ''}`}
              style={{ ['--a' as string]: `var(--${a})`, ['--i' as string]: i } as CSSProperties}>
              <span className="lp-self-name"><span className={`mark mark-${a}`} aria-hidden />{AGENT_META[a].label}</span>
              <span className="lp-self-q">{AGENT_META[a].question}</span>
              <span className="lp-knot" ref={(el) => { knotRefs.current[i] = el }} aria-hidden />
            </li>
          ))}
        </ol>

        <div className="lp-coda">
          <p className="lp-sub">But does all of you?</p>
          <button className="lp-cta" onClick={ask}
            onPointerEnter={() => setLeaning(true)} onPointerLeave={() => setLeaning(false)}
            onFocus={() => setLeaning(true)} onBlur={() => setLeaning(false)}>
            <span>Ask my other selves</span>
            <svg viewBox="0 0 20 20" aria-hidden><path d="M3 10h13M11 4.5 16.5 10 11 15.5" /></svg>
          </button>
        </div>
      </div>
    </section>
  )
}
