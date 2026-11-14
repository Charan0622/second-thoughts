import { motion } from 'framer-motion'
import type { RunState } from './App'

/** The pooled-regret scale: round one (ghost), after negotiation or veto (solid). */
export default function Gauge({ state }: { state: RunState }) {
  const { pool, negotiation, veto } = state
  const pooled = pool?.p
  const after = negotiation?.chosen.p_after
  const vetoed = !!veto?.fired
  const target = vetoed ? Math.max(veto!.p, pooled ?? 0) : after ?? pooled
  if (target == null) return null

  return (
    <div className="scale" role="img" aria-label={`Pooled regret ${target.toFixed(2)}${pooled != null && after != null ? `, from ${pooled.toFixed(2)} in round one` : ''}`}>
      <div className="scale-head">
        <span className="label">Pooled regret</span>
        <span className="scale-value">{target.toFixed(2)}</span>
        {pooled != null && (after != null || vetoed) && (
          <span className="scale-from">{vetoed ? `veto · round one ${pooled.toFixed(2)}` : `from ${pooled.toFixed(2)} in round one`}</span>
        )}
      </div>
      <div className="scale-track">
        <span className="zone zone-buy" style={{ width: '35%' }}>Buy</span>
        <span className="zone zone-cond" style={{ width: '30%' }}>Condition</span>
        <span className="zone zone-wait" style={{ width: '35%' }}>Wait</span>
        {pooled != null && (after != null || vetoed) && <span className="mark mark-ghost" style={{ left: `${pooled * 100}%` }} />}
        <motion.span
          key={state.runId}
          className={`mark ${vetoed ? 'mark-veto' : ''}`}
          initial={{ left: `${(pooled ?? 0.5) * 100}%` }}
          animate={{ left: `${target * 100}%` }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: after != null ? 0.3 : 0 }}
        />
      </div>
    </div>
  )
}
