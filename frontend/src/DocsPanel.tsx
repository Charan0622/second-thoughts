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
  { id: 'bank', hint: 'Statement with balance + upcoming bills', accept: '.pdf,.jpg,.jpeg,.png,.webp,.csv,.xlsx' },
  { id: 'paystub', hint: 'Pay stub (rate, next pay date)', accept: '.pdf,.jpg,.jpeg,.png,.webp' },
  { id: 'savings', hint: 'Savings goal tracker', accept: '.xlsx,.xls,.csv,.pdf,.jpg,.png' },
  { id: 'receipts', hint: 'Receipts for things you own (up to 5)', accept: '.pdf,.eml,.jpg,.jpeg,.png,.webp,.txt', multiple: true },
  { id: 'rules', hint: 'Your own spending rules (text, PDF or a photo of a note)', accept: '.txt,.pdf,.docx,.jpg,.jpeg,.png,.webp' },
]

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
`

export default function DocsPanel({ onChange, openSignal = 0 }: Props) {
  const [open, setOpen] = useState(false)
  useEffect(() => { if (openSignal > 0) setOpen(true) }, [openSignal])
  const [sum, setSum] = useState<Summary | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

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

  useEffect(() => { if (open) load() }, [open, load])

  const upload = useCallback(async (slot: string, files: FileList | null) => {
    if (!files || !files.length) return
    setBusy(`Reading your ${slot} with NDI… (about 5–15 s)`)
    setErr(null)
    try {
      const fd = new FormData()
      Array.from(files).slice(0, 5).forEach((f) => fd.append('files', f))
      const r = await fetch(`/api/docs/${slot}`, { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `HTTP ${r.status}`)
      setSum(await r.json())
      onChange()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [onChange])

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
            <p className="dcp-sub">Upload any of these. NDI reads each one, and your four selves vote on <b>your</b> numbers only: anything you skip is treated as unknown, never filled in from the demo persona. Files stay on this laptop.</p>
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
                    {s.owner === 'yours' ? 'Replace' : 'Upload'}
                    <input type="file" accept={accept} multiple={!!multiple} disabled={!!busy}
                      onChange={(e) => { upload(id, e.target.files); e.target.value = '' }} />
                  </label>
                  <div className="dcp-files">{s.files.join(' · ') || '—'}</div>
                  {s.errors.map((x) => <div className="dcp-err" key={x}>{x}</div>)}
                </div>
              )
            })}
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
