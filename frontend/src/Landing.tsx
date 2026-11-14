import type { DemoItem } from './api'
import { AGENT_META } from './Council'

interface Props {
  item?: DemoItem
  onStart: () => void
  onDemo: () => void
  mock: boolean
}

/** The first viewport: one object, four quiet presences, one question. */
export default function Landing({ item, onStart, onDemo, mock }: Props) {
  return (
    <section className="landing" aria-label="Second Thoughts">
      <header className="landing-mast">
        <span className="wordmark"><span className="brand-mark" aria-hidden><i /><i /></span>Second Thoughts</span>
        <span className={`source ${mock ? 'source-mock' : 'source-live'}`}>{mock ? 'Mock fixtures' : 'Live'}</span>
      </header>

      <div className="landing-stage">
        <h1 className="landing-title rise">Want it?<br /><em>Ask all of you.</em></h1>

        {item && (
          <figure className="specimen settle">
            <img src={item.frame_url} alt={item.name} />
            <figcaption>
              <span>{item.name}</span>
              <b>${item.price.toLocaleString('en-US')}</b>
            </figcaption>
          </figure>
        )}

        <div className="presences" aria-hidden>
          {(['budget', 'goals', 'owned', 'deal'] as const).map((a, i) => (
            <span key={a} className={`presence presence-${a} fade`} style={{ ['--a' as string]: `var(--${a})`, animationDelay: `${900 + i * 180}ms` }}>
              <span className={`mark mark-${a}`} />{AGENT_META[a].question}
            </span>
          ))}
        </div>

        <div className="landing-copy enter" style={{ animationDelay: '350ms' }}>
          <p className="landing-sub">Four perspectives. One decision you can live with.</p>
          <p className="landing-detail">Point your camera at something you’re about to buy. Your budget, your goals, what you already own and the going price each weigh in from your own documents, then agree on one answer.</p>
          <div className="landing-actions">
            <button className="cta" onClick={onStart}>Get a second thought <span aria-hidden>→</span></button>
            <button className="cta-quiet" onClick={onDemo}>Try the live demo</button>
          </div>
        </div>
      </div>
    </section>
  )
}
