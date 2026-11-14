// First visit: nobody's documents are chosen yet (persona mode "none"), so the council can't run.
// Pick one: upload your own documents, or try the demo persona (Maya). Sits where the camera normally is.
interface Props {
  onUpload: () => void
  onDemo: () => void
  busy?: boolean
}

const CSS = `
.onb { align-items: center; text-align: center; }
.onb-title { font: 400 1.6rem/1.15 var(--serif); margin: 0; }
.onb-sub { margin: 0; color: var(--ink-2); font-size: 0.92rem; }
.onb-list { margin: 0; padding: 0; list-style: none; color: var(--ink-3); font-size: 0.8rem; }
.onb-actions { display: flex; flex-direction: column; align-items: center; gap: var(--s3, 18px); }
`

export default function Onboarding({ onUpload, onDemo, busy }: Props) {
  return (
    <section className="desire onb" aria-label="Choose whose documents to use">
      <style>{CSS}</style>
      <h1 className="onb-title">Whose money is this?</h1>
      <p className="onb-sub">Your four selves need documents to argue from. Choose one to start — until then the council can’t run.</p>
      <div className="onb-actions">
        <button className="cta" onClick={onUpload} disabled={busy}>📄 Upload your documents</button>
        <ul className="onb-list"><li>bank statement · pay stub · receipts + a few quick questions</li></ul>
        <button className="cta-quiet" onClick={onDemo} disabled={busy}>Try the demo persona (Maya)</button>
      </div>
    </section>
  )
}
