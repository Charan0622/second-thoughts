// "No price in the photo — online it's about $X. Is that right?" → confirm or type your own, then the council runs.
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

export interface ConfirmPriceEvent {
  type: 'confirm_price'
  item_name: string
  category?: string
  suggested_price: number | null
  sources: { host: string; price: number }[]
  message: string
}

const CSS = `
.pc-scrim { position: fixed; inset: 0; z-index: 1050; background: rgba(22,20,15,.5); display: grid; place-items: center; padding: 16px; }
.pc-card { background: var(--ivory, #f4efe4); color: var(--ink, #1c1a17); border-radius: 10px; padding: 24px; width: min(440px, 100%);
  display: grid; gap: 12px; box-shadow: 0 20px 60px rgba(0,0,0,.35); font-family: var(--sans, system-ui); }
.pc-title { font: 400 1.4rem/1.15 var(--serif, Georgia); margin: 0; }
.pc-msg { margin: 0; font-size: .95rem; color: var(--ink-2, #4a463f); }
.pc-src { margin: 0; padding: 0; list-style: none; display: flex; flex-wrap: wrap; gap: 6px; }
.pc-src li { font: .75rem/1 var(--mono, monospace); padding: 5px 8px; border-radius: 999px; border: 1px solid var(--hair-2, #d8d2c4); }
.pc-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pc-yes { font: 500 .95rem/1 var(--sans, system-ui); padding: 11px 16px; border-radius: 999px; border: 0; background: var(--ink, #1c1a17); color: var(--ivory, #f4efe4); cursor: pointer; }
.pc-in { font: .95rem var(--sans, system-ui); padding: 9px 10px; border: 1px solid var(--hair-2, #d8d2c4); border-radius: 8px; width: 120px; background: #fff; }
.pc-go { font: 500 .9rem/1 var(--sans, system-ui); padding: 10px 14px; border-radius: 999px; border: 1px solid var(--ink, #1c1a17); background: none; color: var(--ink, #1c1a17); cursor: pointer; }
.pc-x { justify-self: start; background: none; border: 0; color: var(--ink-2, #4a463f); text-decoration: underline; cursor: pointer; font-size: .85rem; }
`

export default function PriceConfirm({ ev, onConfirm, onCancel }: { ev: ConfirmPriceEvent | null; onConfirm: (price: number, name: string) => void; onCancel: () => void }) {
  const [own, setOwn] = useState('')
  useEffect(() => { setOwn('') }, [ev])
  if (!ev) return null
  const typed = Number(own.replace(/[$,\s]/g, ''))
  return createPortal(
    <div className="pc-scrim" role="dialog" aria-modal="true" aria-label="Confirm the price">
      <style>{CSS}</style>
      <div className="pc-card">
        <p className="pc-title">{ev.item_name}</p>
        <p className="pc-msg">{ev.message}</p>
        {ev.sources.length > 0 && (
          <ul className="pc-src">{ev.sources.map((s) => <li key={s.host}>{s.host} · ${s.price.toLocaleString()}</li>)}</ul>
        )}
        <div className="pc-row">
          {ev.suggested_price != null && (
            <button type="button" className="pc-yes" autoFocus onClick={() => onConfirm(ev.suggested_price!, ev.item_name)}>
              Yes, ${ev.suggested_price.toLocaleString()} — ask my selves
            </button>
          )}
        </div>
        <div className="pc-row">
          <span className="pc-msg">{ev.suggested_price != null ? 'Or the price I see is' : 'The price is'} $</span>
          <input className="pc-in" inputMode="decimal" value={own} placeholder="0.00" onChange={(e) => setOwn(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && typed > 0) onConfirm(typed, ev.item_name) }} />
          <button type="button" className="pc-go" disabled={!(typed > 0)} onClick={() => onConfirm(typed, ev.item_name)}>Use this price</button>
        </div>
        <button type="button" className="pc-x" onClick={onCancel}>Cancel</button>
      </div>
    </div>,
    document.body,
  )
}
