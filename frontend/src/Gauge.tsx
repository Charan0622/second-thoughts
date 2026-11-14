import { AnimatePresence, motion } from 'framer-motion'
import type { RunState } from './App'
import type { NegotiationEvent, Offer } from './api'

const MAX_OFFERS = 3

/** Chosen offer first, then the best runners-up by pooled p (or in given order). */
function visibleOffers(n: NegotiationEvent): Offer[] {
  const score = (o: Offer) => n.pooled_by_offer?.[o.id] ?? 1
  const rest = n.offers.filter((o) => o.id !== n.chosen.id).sort((a, b) => score(a) - score(b))
  const chosen = n.offers.find((o) => o.id === n.chosen.id) ?? { id: n.chosen.id, label: n.chosen.label, amount: n.chosen.amount ?? null }
  return [chosen, ...rest].slice(0, MAX_OFFERS)
}

export default function Gauge({ state }: { state: RunState }) {
  const { pool, negotiation, veto } = state
  const pooled = pool?.p
  const after = negotiation?.chosen.p_after
  const target = veto?.fired ? Math.max(veto.p, pooled ?? 0) : after ?? pooled
  const vetoed = !!veto?.fired

  return (
    <div className="panel gauge-panel">
      <div className="gauge-row">
        <div className="gauge-title">
          <span className="panel-title">Pooled regret</span>
          <span className="gauge-value">{target != null ? target.toFixed(2) : '—'}</span>
        </div>
        <div className="gauge">
          <div className="gauge-track">
            <span className="band band-buy" style={{ width: '35%' }}><span>Buy</span></span>
            <span className="band band-cond" style={{ width: '30%' }}><span>Condition</span></span>
            <span className="band band-wait" style={{ width: '35%' }}><span>Wait</span></span>
          </div>
          <div className="gauge-axis" aria-hidden>
            {[0, 0.35, 0.65, 1].map((v) => <span key={v} style={{ left: `${v * 100}%` }}>{v === 0 || v === 1 ? v : v.toFixed(2)}</span>)}
          </div>
          {pooled != null && after != null && (
            <span className="needle-ghost" style={{ left: `${pooled * 100}%` }} title={`pooled ${pooled.toFixed(2)}`} />
          )}
          <AnimatePresence>
            {target != null && (
              <motion.div
                key={state.runId}
                className={`needle ${vetoed ? 'needle-veto' : ''}`}
                initial={{ left: '50%', opacity: 0 }}
                animate={{ left: `${target * 100}%`, opacity: 1 }}
                transition={{ type: 'spring', stiffness: 90, damping: 14, delay: after != null ? 0.6 : 0 }}
              >
                <span className="needle-head" />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <AnimatePresence>
        {negotiation && (
          <motion.div className="negotiation" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            <span className="neg-title">Negotiating</span>
            <div className="offers">
              {visibleOffers(negotiation).map((o, i) => {
                const chosen = o.id === negotiation.chosen.id
                const op = negotiation.pooled_by_offer?.[o.id]
                return (
                  <motion.span
                    key={o.id}
                    className={`chip offer ${chosen ? 'chosen' : ''}`}
                    title={o.label}
                    initial={{ opacity: 0, y: 8 }}
                    animate={chosen ? { opacity: 1, y: 0, scale: [1, 1.08, 1] } : { opacity: 0.6, y: 0 }}
                    transition={{ delay: 0.08 * i + (chosen ? 0.35 : 0), duration: 0.4 }}
                  >
                    <span className="offer-text">{chosen && '✓ '}{o.label}</span>
                    {op != null && <span className="offer-p">{op.toFixed(2)}</span>}
                  </motion.span>
                )
              })}
              {negotiation.offers.length > MAX_OFFERS && <span className="meta">+{negotiation.offers.length - MAX_OFFERS} tried</span>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
