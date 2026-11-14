import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { fetchLedger, type Ledger as LedgerT } from './api'
import { mockLedger } from './mock'

const ROWS: { key: string; label: string; what: string }[] = [
  { key: 'drex', label: 'Drex', what: 'votes · perceive' },
  { key: 'ndi', label: 'NDI', what: 'documents · price' },
  { key: 'keenable', label: 'Keenable', what: 'live prices' },
  { key: 'deepinfra', label: 'DeepInfra', what: 'verdict sentence' },
  { key: 'intern', label: 'Intern', what: 'the Clerk' },
]

const fmtMs = (ms?: number | null) => (ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`)

export default function Ledger({ mock }: { mock: boolean }) {
  const [data, setData] = useState<LedgerT | null>(null)
  const [stale, setStale] = useState(false)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const d = mock ? mockLedger() : await fetchLedger()
        if (alive) { setData(d); setStale(false) }
      } catch {
        if (alive) setStale(true)
      }
    }
    void tick()
    const id = setInterval(tick, mock ? 700 : 2000)
    return () => { alive = false; clearInterval(id) }
  }, [mock])

  return (
    <footer className="ledger" aria-label="Tool ledger">
      <p className="ledger-title">
        <span className="label">Under the hood</span>
        <span className="ledger-state">{mock ? 'mock counts' : stale ? 'ledger offline' : 'live counts'}</span>
      </p>
      <ul className="ledger-tools">
        {ROWS.map((r) => {
          const t = data?.tools[r.key]
          const offline = t?.note && t.calls === 0
          return (
            <li key={r.key}>
              <span className="tool">{r.label}</span>
              <motion.span key={t?.calls ?? -1} className="calls" initial={{ opacity: 0.3, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
                {t?.calls ?? '—'}
              </motion.span>
              <span className="what">{offline ? 'offline assets' : `${r.what} · ${fmtMs(t?.ms_median)}`}{t?.errors ? ` · ${t.errors} err` : ''}</span>
            </li>
          )
        })}
      </ul>
      {data && <p className="ledger-sum"><b>{data.verdicts}</b> verdicts · ≈ <b>${data.cost_usd_est.toFixed(3)}</b> spent</p>}
    </footer>
  )
}
