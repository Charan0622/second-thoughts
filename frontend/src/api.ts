// Typed backend contract — mirrors docs/API.md exactly.

export type AgentId = 'budget' | 'goals' | 'owned' | 'deal'
export type Band = 'buy' | 'buy_with_condition' | 'wait'
export type DemoItemId = 'shoes' | 'headphones' | 'macmini'

export const AGENTS: AgentId[] = ['budget', 'goals', 'owned', 'deal']

export interface Citation {
  doc: string
  doc_label: string
  page: number | null
  quote: string
  bbox: [number, number, number, number] | null
  crop_url: string | null
}

export interface PerceiveStartEvent { type: 'perceive_start' }
export interface PerceiveEvent {
  type: 'perceive'
  item_name: string
  category: string
  category_p: number
  price_bucket: string
  price: number | null
  price_source: 'ndi' | 'manual' | 'cache' | 'bucket'
  ms: number
}
export interface CouncilStartEvent { type: 'council_start'; agents: AgentId[] }
export interface VoteEvent {
  type: 'vote'
  agent: AgentId
  label: string
  p_regret: number
  stake: number
  stance: 'buy' | 'wait' | 'abstain'
  headline: string
  citation: Citation
  cite_p?: number
  model: string
  ms: number
}
export interface VetoEvent {
  type: 'veto'
  agent: AgentId
  p: number
  threshold: number
  fired: boolean
  reason: string
}
export interface PoolEvent {
  type: 'pool'
  p: number
  band: Band
  weights: Partial<Record<AgentId, number>>
}
export interface Offer { id: string; label: string; amount: number | null }
export interface Pick { agent: AgentId; offer_id: string; p_before: number; p_after: number }
export interface NegotiationEvent {
  type: 'negotiation'
  offers: Offer[]
  picks: Pick[]
  chosen: { id: string; label: string; p_after: number; amount?: number | null }
  pooled_by_offer?: Record<string, number>
  ms: number
}
export interface PriceTerms {
  hours_of_work: number
  japan_slip_days: number
  japan_slip_if_from_savings?: number
  goal_name?: string
  pct_free_cash: number
}
export interface VerdictEvent {
  type: 'verdict'
  band: Band
  title: string
  p: number
  condition: string | null
  tally: { buy: number; wait: number }
  price_terms: PriceTerms
  total_ms: number
  council_ms?: number
  p_round_one?: number
  veto?: boolean
  item?: { name: string; price: number | null; category: string }
}
export interface SentenceEvent { type: 'sentence'; text: string; source: 'deepinfra' | 'template' }
export interface DoneEvent { type: 'done' }
export interface ErrorEvent { type: 'error'; message: string }
export interface AgentErrorEvent { type: 'agent_error'; message: string; agent?: AgentId }

export type VerdictStreamEvent =
  | PerceiveStartEvent
  | PerceiveEvent
  | CouncilStartEvent
  | VoteEvent
  | VetoEvent
  | PoolEvent
  | NegotiationEvent
  | VerdictEvent
  | SentenceEvent
  | DoneEvent
  | ErrorEvent
  | AgentErrorEvent

export interface VerdictRequest {
  demo_item: DemoItemId | null
  frame: string | null
  price: number | null
  item_name: string | null
}

export interface DemoItem { id: DemoItemId; name: string; price: number; frame_url: string }

export interface LedgerTool {
  calls: number
  errors?: number
  ms_median?: number | null
  input_tokens?: number | null
  cost_usd?: number
  note?: string
}
export interface Ledger {
  tools: Record<string, LedgerTool>
  verdicts: number
  cost_usd_est: number
}

export interface Persona {
  name: string
  free_cash: number
  next_payday: string
  japan: { target: number; saved: number; monthly: number }
  rules: string[]
}

export function bandOf(p: number): Band {
  if (p < 0.35) return 'buy'
  if (p <= 0.65) return 'buy_with_condition'
  return 'wait'
}

/** POST /api/verdict and yield each NDJSON line as a typed event. */
export async function* streamVerdict(
  req: VerdictRequest,
  signal: AbortSignal,
): AsyncGenerator<VerdictStreamEvent> {
  const res = await fetch('/api/verdict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => '')
    throw new Error(`Backend ${res.status}: ${text.slice(0, 160) || res.statusText}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let nl: number
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      if (line) yield parseLine(line)
    }
  }
  const tail = (buf + decoder.decode()).trim()
  if (tail) yield parseLine(tail)
}

function parseLine(line: string): VerdictStreamEvent {
  try {
    return JSON.parse(line) as VerdictStreamEvent
  } catch {
    return { type: 'error', message: `Bad stream line: ${line.slice(0, 80)}` }
  }
}

async function getJSON<T>(url: string, timeoutMs = 2500): Promise<T> {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const res = await fetch(url, { signal: ctl.signal })
    if (!res.ok) throw new Error(`${url} → ${res.status}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(t)
  }
}

export const fetchHealth = () => getJSON<{ ok: boolean; facts_loaded?: boolean }>('/api/health', 1500)
export const fetchDemoItems = () => getJSON<DemoItem[]>('/api/demo_items')
export const fetchLedger = () => getJSON<Ledger>('/api/ledger', 1800)
/** POST /api/explain — Intern ("the Clerk") explains the last verdict. Slow: 5–30 s. */
export async function fetchExplain(signal?: AbortSignal): Promise<string> {
  const res = await fetch('/api/explain', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', signal,
  })
  const d = (await res.json().catch(() => ({}))) as { ok?: boolean; text?: string; message?: string; detail?: string }
  if (!res.ok || d.ok === false || !d.text) throw new Error(d.message || d.detail || `Clerk failed (${res.status})`)
  return d.text
}

export const fetchPersona = () => getJSON<Persona>('/api/persona')
