import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { fetchLedger, type Ledger as LedgerT } from './api'
import { mockLedger } from './mock'

const ROWS: { key: string; label: string; what: string }[] = [
  { key: 'drex', label: 'Drex', what: 'votes · perceive' },
  { key: 'ndi', label: 'NDI', what: 'docs · price read' },
  { key: 'intern', label: 'Intern', what: 'clerk' },
  { key: 'keenable', label: 'Keenable', what: 'live prices' },
  { key: 'deepinfra', label: 'DeepInfra', what: 'verdict sentence' },
  { key: 'adobe', label: 'Adobe', what: 'avatars · slides' },
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
    <div className="panel ledger">
      <div className="ledger-head">
        <span className="panel-title">Tool ledger</span>
        <span className="meta">{stale ? 'offline' : 'live'}</span>
      </div>
      <table>
        <thead>
          <tr><th>Tool</th><th className="num">Calls</th><th className="num">Median</th></tr>
        </thead>
        <tbody>
          {ROWS.map((r) => {
            const t = data?.tools[r.key]
            return (
              <tr key={r.key}>
                <td><span className="tool-name">{r.label}</span> <span className="tool-what">{t?.note && t.calls === 0 ? 'offline assets' : r.what}</span></td>
                <td className="num">
                  <motion.span
                    key={t?.calls ?? -1}
                    className="calls"
                    initial={{ y: -10, opacity: 0.2, color: '#fcc451' }}
                    animate={{ y: 0, opacity: 1, color: '#f0efec' }}
                    transition={{ duration: 0.5 }}
                  >
                    {t?.calls ?? '—'}
                  </motion.span>
                  {t?.errors ? <span className="errs"> ({t.errors} err)</span> : null}
                </td>
                <td className="num muted">{fmtMs(t?.ms_median)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {data && (
        <div className="ledger-foot">
          <span><b>{data.verdicts}</b> verdicts</span>
          <span>≈ <b>${data.cost_usd_est.toFixed(3)}</b> spent</span>
        </div>
      )}
    </div>
  )
}
