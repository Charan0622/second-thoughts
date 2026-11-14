import { useState } from 'react'
import type { VerdictEvent } from './api'
import './TwoFutures.css'

/* TWO FUTURES. ONE DECISION.
   Two Adobe Firefly artworks: conceptual interpretations of buying now and of waiting.
   They illustrate the verdict; they never decide it. Which side is marked comes only
   from the council's `band`, and a conditional verdict shows its condition in full. */

type Side = 'buy' | 'wait'

const ART: Record<Side, { src: string; title: string; alt: string }> = {
  buy: { src: '/futures/future-buy.webp', title: 'If you buy it.', alt: 'An artistic interpretation of the future in which you buy it now' },
  wait: { src: '/futures/future-wait.webp', title: 'If you wait.', alt: 'An artistic interpretation of the future in which you wait' },
}

export default function TwoFutures({ verdict }: { verdict: VerdictEvent }) {
  const chosen: Side = verdict.band === 'wait' ? 'wait' : 'buy'
  const conditional = verdict.band === 'buy_with_condition'
  const [active, setActive] = useState<Side>(chosen)
  // Each artwork is 'pending' until the browser has really decoded it; the Firefly credit only shows for loaded art.
  const [art, setArt] = useState<Record<Side, 'pending' | 'ok' | 'missing'>>({ buy: 'pending', wait: 'pending' })
  const missing = { buy: art.buy === 'missing', wait: art.wait === 'missing' }
  const anyArt = art.buy === 'ok' || art.wait === 'ok'

  return (
    <section className="futures" id="two-futures" aria-labelledby="futures-title">
      <div className="futures-inner">
        <header className="futures-head">
          <h2 id="futures-title">Two futures. <em>One decision.</em></h2>
          <p className="futures-says">
            {conditional ? <>The council says yes, on one condition: <b>{verdict.condition ?? verdict.title}</b></>
              : chosen === 'buy' ? <>The council says <b>buy it</b>.</>
              : <>The council says <b>wait</b>{verdict.condition ? <>: {verdict.condition}</> : null}.</>}
          </p>
        </header>

        <div className="diptych" data-active={active}>
          {(['buy', 'wait'] as const).map((side) => {
            const a = ART[side]
            const isChosen = side === chosen
            return (
              <button
                key={side}
                type="button"
                className={`future future-${side} ${isChosen ? 'is-chosen' : ''} ${active === side ? 'is-active' : ''} ${missing[side] ? 'is-missing' : ''}`}
                aria-pressed={active === side}
                onClick={() => setActive(side)}
                onMouseEnter={() => setActive(side)}
                onFocus={() => setActive(side)}
              >
                {!missing[side] && (
                  <img src={a.src} alt={a.alt}
                    onLoad={() => setArt((m) => ({ ...m, [side]: 'ok' }))}
                    onError={() => setArt((m) => ({ ...m, [side]: 'missing' }))} />
                )}
                <span className="future-caption">
                  {isChosen && (
                    <span className="future-mark">{conditional ? 'The council’s choice, if the condition is met' : 'The council’s choice'}</span>
                  )}
                  <span className="future-title">{a.title}</span>
                </span>
              </button>
            )
          })}
        </div>

        <footer className="futures-foot">
          {conditional && <p className="futures-note">Neither future is guaranteed. The first only holds if you keep the condition.</p>}
          <p className="futures-credit">
            {anyArt ? 'Future visualizations created with Adobe Firefly. ' : ''}
            Artistic interpretations, not predictions. The verdict comes from the council, not the artwork.
          </p>
        </footer>
      </div>
    </section>
  )
}
