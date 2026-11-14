// "Your documents": upload your own documents, slot by slot. The first upload switches the persona mode to
// "mine": only your files are used, and a slot you skip is treated as unknown (never the demo persona's data).
// Each upload goes to the backend, NDI extracts it right away. Files stay on this machine (data/private/my_docs).
import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { PersonaMode } from './api'

interface Slot { label: string; owner: 'yours' | 'demo' | 'missing'; files: string[]; errors: string[] }
interface Summary { mode?: PersonaMode; slots: Record<string, Slot>; flags: string[]; name: string; free_cash: number }

interface Props {
  onChange: () => void
  /** Bump to open the panel from outside (the onboarding card's "Upload your documents"). */
  openSignal?: number
}

const ORDER: { id: string; hint: string; accept: string; multiple?: boolean }[] = [
  { id: 'bank', hint: 'Statement with your balance and upcoming bills', accept: '.pdf,.jpg,.jpeg,.png,.webp,.csv,.xlsx' },
  { id: 'paystub', hint: 'Your latest pay stub (rate, next pay date)', accept: '.pdf,.jpg,.jpeg,.png,.webp' },
  { id: 'receipts', hint: 'Receipts for things you own. Each one you add is kept, so the list grows.', accept: '.pdf,.eml,.jpg,.jpeg,.png,.webp,.txt', multiple: true },
]

interface Profile { goal_name?: string; goal_target?: number | string; goal_saved?: number | string; goal_monthly?: number | string; goal_date?: string; rules?: string[] | string }

const CSS = `
.dcp-btn { align-self: center; font: 500 0.78rem/1 var(--sans); padding: 7px 12px; border-radius: 999px;
  border: 1px solid var(--hair-2); background: transparent; color: var(--ink-2); white-space: nowrap; }
.dcp-btn:hover { border-color: var(--ink); color: var(--ink); }
.dcp-btn.is-mine { border-color: var(--buy); color: var(--buy); }
.dcp-scrim { position: fixed; inset: 0; z-index: 1000; background: rgba(22, 20, 15, 0.55); display: grid; place-items: center; padding: var(--gutter); }
.dcp-card { background: var(--ivory, #f4efe4); color: var(--ink); border-radius: 10px; padding: var(--s5, 30px); width: min(620px, 100%);
  max-height: 90vh; overflow: auto; display: grid; gap: var(--s3, 18px); box-shadow: 0 20px 60px rgba(0,0,0,.35); font-family: var(--sans); }
.dcp-head { display: flex; justify-content: space-between; align-items: baseline; gap: var(--s3, 18px); }
.dcp-title { font: 400 1.5rem/1.1 var(--serif); }
.dcp-x { background: none; border: 0; font-size: 1.3rem; line-height: 1; color: var(--ink-2); padding: 4px; }
.dcp-sub { font-size: 0.85rem; color: var(--ink-2); margin: 0; }
.dcp-row { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; align-items: center; padding: 10px 0; border-top: 1px solid var(--hair-2); }
.dcp-name { font-weight: 600; }
.dcp-tag { font: 500 0.7rem/1 var(--sans); padding: 3px 7px; border-radius: 999px; margin-left: 6px; border: 1px solid var(--hair-2); color: var(--ink-2); }
.dcp-tag.yours { border-color: var(--buy); color: var(--buy); }
.dcp-files { grid-column: 1 / -1; font: 0.78rem/1.3 var(--mono, monospace); color: var(--ink-2); word-break: break-all; }
.dcp-hint { font-size: 0.8rem; color: var(--ink-2); }
.dcp-up { font: 500 0.78rem/1 var(--sans); padding: 7px 12px; border-radius: 6px; border: 1px solid var(--ink); background: var(--ink); color: var(--ivory, #f4efe4); cursor: pointer; }
.dcp-up input { display: none; }
.dcp-flags { margin: 0; padding: 10px 12px; border-radius: 6px; background: rgba(200,140,0,.12); font-size: 0.82rem; list-style: none; display: grid; gap: 4px; }
.dcp-err { color: var(--wait); font-size: 0.8rem; grid-column: 1 / -1; }
.dcp-foot { display: flex; justify-content: space-between; align-items: center; gap: var(--s3, 18px); font-size: 0.8rem; color: var(--ink-2); }
.dcp-reset { background: none; border: 1px solid var(--hair-2); border-radius: 6px; padding: 6px 10px; font: inherit; color: var(--ink-2); cursor: pointer; }
.dcp-busy { font-size: 0.85rem; }
.dcp-q { display: grid; gap: 10px; padding: 12px 0 4px; border-top: 1px solid var(--hair-2); }
.dcp-q h3 { margin: 0; font: 600 0.95rem/1.2 var(--sans); }
.dcp-q .dcp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.dcp-q label { display: grid; gap: 4px; font-size: 0.8rem; color: var(--ink-2); }
.dcp-q input, .dcp-q textarea { font: 0.9rem/1.3 var(--sans); padding: 7px 9px; border: 1px solid var(--hair-2); border-radius: 6px; background: #fff; color: var(--ink); }
.dcp-q textarea { min-height: 64px; resize: vertical; }
.dcp-q .dcp-sug { font-size: 0.75rem; color: var(--buy); }
.dcp-save { justify-self: start; font: 500 0.82rem/1 var(--sans); padding: 8px 14px; border-radius: 6px; border: 1px solid var(--ink); background: var(--ink); color: var(--ivory, #f4efe4); cursor: pointer; }
.dcp-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.dcp-chip { font: 0.75rem/1 var(--sans); padding: 5px 8px; border-radius: 999px; border: 1px dashed var(--hair-2); background: none; color: var(--ink-2); cursor: pointer; }
`

export default function DocsPanel({ onChange, openSignal = 0 }: Props) {
  const [open, setOpen] = useState(false)
  useEffect(() => { if (openSignal > 0) setOpen(true) }, [openSignal])
  const [sum, setSum] = useState<Summary | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [q, setQ] = useState<Profile>({})
  const [sugMonthly, setSugMonthly] = useState<number | null>(null)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/docs')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setSum(await r.json())
      setErr(null)
    } catch (e) {
      setErr(`Documents need the live backend (${e instanceof Error ? e.message : String(e)})`)
    }
  }, [])

  const loadProfile = useCallback(async () => {
    try {
      const r = await fetch('/api/profile')
      if (!r.ok) return
      const j = await r.json()
      const p: Profile = j.profile ?? {}
      setQ({ ...p, rules: Array.isArray(p.rules) ? p.rules.join('\n') : (p.rules ?? '') })
      setSugMonthly(j.suggested?.goal_monthly ?? null)
    } catch { /* offline */ }
  }, [])

  useEffect(() => { if (open) { load(); loadProfile() } }, [open, load, loadProfile])

  const saveAnswers = useCallback(async () => {
    setBusy('Saving your answers…'); setErr(null); setSaved(false)
    try {
      const body = { ...q, goal_monthly: q.goal_monthly === '' || q.goal_monthly == null ? sugMonthly ?? '' : q.goal_monthly }
      const r = await fetch('/api/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setSum(await r.json()); setSaved(true); onChange()
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setBusy(null) }
  }, [q, sugMonthly, onChange])

  const clearReceipts = useCallback(async () => {
    setBusy('Removing receipts…')
    try { const r = await fetch('/api/docs?slot=receipts', { method: 'DELETE' }); if (r.ok) { setSum(await r.json()); onChange() } } finally { setBusy(null) }
  }, [onChange])

  const upload = useCallback(async (slot: string, files: FileList | null) => {
    if (!files || !files.length) return
    setBusy(`Reading your ${slot} with NDI… (about 5–15 s)`)
    setErr(null)
    try {
      const fd = new FormData()
      Array.from(files).slice(0, 10).forEach((f) => fd.append('files', f))
      const r = await fetch(`/api/docs/${slot}`, { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `HTTP ${r.status}`)
      setSum(await r.json())
      onChange()
      if (slot === 'bank') loadProfile()   // the statement may reveal your monthly saving
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [onChange, loadProfile])

  const reset = useCallback(async () => {
    setBusy('Removing your documents…')
    try {
      const r = await fetch('/api/docs', { method: 'DELETE' })
      if (r.ok) { setSum(await r.json()); onChange() }
    } finally {
      setBusy(null)
    }
  }, [onChange])

  const mine = sum ? (sum.mode ? sum.mode === 'mine' : Object.values(sum.slots).some((s) => s.owner === 'yours')) : false

  return (
    <>
      <style>{CSS}</style>
      <button type="button" className={`dcp-btn${mine ? ' is-mine' : ''}`} onClick={() => setOpen(true)}>
        📄 {mine ? 'Your documents' : 'Use my documents'}
      </button>
      {open && createPortal(
        <div className="dcp-scrim" role="dialog" aria-modal="true" aria-label="Your documents" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false) }}>
          <div className="dcp-card">
            <div className="dcp-head">
              <span className="dcp-title">Your documents</span>
              <button type="button" className="dcp-x" aria-label="Close" onClick={() => setOpen(false)}>×</button>
            </div>
            <p className="dcp-sub">Upload your <b>bank statement</b> and <b>pay stub</b>, add <b>receipts</b> for things you own, then answer a few quick questions. NDI reads every document, and your four selves vote on <b>your</b> numbers only. Files stay on this laptop.</p>
            {busy && <p className="dcp-busy">⏳ {busy}</p>}
            {err && <p className="dcp-err">{err}</p>}
            {sum && ORDER.map(({ id, hint, accept, multiple }) => {
              const s = sum.slots[id]
              if (!s) return null
              return (
                <div className="dcp-row" key={id}>
                  <div>
                    <span className="dcp-name">{s.label}</span>
                    <span className={`dcp-tag ${s.owner}`}>{s.owner === 'yours' ? 'yours' : s.owner === 'missing' ? 'not uploaded' : 'demo'}</span>
                    <div className="dcp-hint">{hint}</div>
                  </div>
                  <label className="dcp-up">
                    {id === 'receipts' ? (s.owner === 'yours' ? '+ Add more' : 'Add receipts') : s.owner === 'yours' ? 'Replace' : 'Upload'}
                    <input type="file" accept={accept} multiple={!!multiple} disabled={!!busy}
                      onChange={(e) => { upload(id, e.target.files); e.target.value = '' }} />
                  </label>
                  <div className="dcp-files">{s.files.join(' · ') || '—'}
                    {id === 'receipts' && s.owner === 'yours' && <> · <button type="button" className="dcp-chip" onClick={clearReceipts} disabled={!!busy}>clear receipts</button></>}
                  </div>
                  {s.errors.map((x) => <div className="dcp-err" key={x}>{x}</div>)}
                </div>
              )
            })}
            {sum && (
              <div className="dcp-q">
                <h3>A few quick questions</h3>
                <div className="dcp-grid">
                  <label>What are you saving for?<input value={String(q.goal_name ?? '')} placeholder="e.g. Japan trip, emergency fund" onChange={(e) => setQ({ ...q, goal_name: e.target.value })} /></label>
                  <label>By when?<input value={String(q.goal_date ?? '')} placeholder="e.g. April 2027" onChange={(e) => setQ({ ...q, goal_date: e.target.value })} /></label>
                  <label>Target amount ($)<input inputMode="decimal" value={String(q.goal_target ?? '')} placeholder="4000" onChange={(e) => setQ({ ...q, goal_target: e.target.value })} /></label>
                  <label>Saved so far ($)<input inputMode="decimal" value={String(q.goal_saved ?? '')} placeholder="0" onChange={(e) => setQ({ ...q, goal_saved: e.target.value })} /></label>
                  <label>Saving per month ($)<input inputMode="decimal" value={String(q.goal_monthly ?? '')} placeholder={sugMonthly != null ? String(sugMonthly) : '200'} onChange={(e) => setQ({ ...q, goal_monthly: e.target.value })} />
                    {sugMonthly != null && <span className="dcp-sug">From your bank statement: about ${sugMonthly.toLocaleString()} in savings transfers</span>}</label>
                </div>
                <label>Any spending rules you want held to? (one per line, optional)
                  <textarea value={String(q.rules ?? '')} placeholder={'e.g. No gadgets over $200 until my trip\nMax two takeout orders a week'} onChange={(e) => setQ({ ...q, rules: e.target.value })} /></label>
                <div className="dcp-chips">
                  {['No gadgets over $200 until my goal', 'No clothing over $100 this month', 'Max two takeout orders a week'].map((c) => (
                    <button type="button" key={c} className="dcp-chip" onClick={() => setQ({ ...q, rules: [String(q.rules ?? '').trim(), c].filter(Boolean).join('\n') })}>+ {c}</button>
                  ))}
                </div>
                <button type="button" className="dcp-save" onClick={saveAnswers} disabled={!!busy}>{saved ? 'Saved ✓' : 'Save answers'}</button>
              </div>
            )}
            {sum && sum.flags.length > 0 && (
              <ul className="dcp-flags">{sum.flags.map((f) => <li key={f}>⚠ {f}</li>)}</ul>
            )}
            {sum && (
              <div className="dcp-foot">
                <span>{sum.mode === 'none' ? 'No documents yet' : <>{sum.name} · free cash before payday <b>${sum.free_cash.toLocaleString()}</b></>}</span>
                {mine && <button type="button" className="dcp-reset" onClick={reset} disabled={!!busy}>Remove my documents</button>}
              </div>
            )}
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}
