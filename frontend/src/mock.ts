// Offline stand-in for the backend. Emits the same NDJSON event sequence as
// POST /api/verdict with realistic timings, so the UI can be demoed without it.
import type {
  AgentId, DemoItem, DemoItemId, Ledger, Persona, VerdictRequest, VerdictStreamEvent, VoteEvent,
} from './api'

export const MOCK_DEMO_ITEMS: DemoItem[] = [
  { id: 'shoes', name: 'ASICS Gel-Nimbus 27 Running Shoes', price: 109.95, frame_url: '/demo_frames/price_tag_shoes.jpg' },
  { id: 'headphones', name: 'Sony WH-1000XM6 Headphones', price: 349, frame_url: '/demo_frames/price_tag_headphones.jpg' },
  { id: 'macmini', name: 'Apple Mac mini (M5, 16GB)', price: 599, frame_url: '/demo_frames/price_tag_macmini.jpg' },
]

export const MOCK_PERSONA: Persona = {
  name: 'Maya Chen',
  free_cash: 425,
  next_payday: '2026-11-27',
  japan: { target: 4000, saved: 2600, monthly: 280 },
  rules: ['No gadgets over $200 before Japan. Running gear is exempt.'],
}

const ledger: Ledger = {
  tools: {
    drex: { calls: 36, errors: 0, ms_median: 284, input_tokens: 13900 },
    ndi: { calls: 7, errors: 0, ms_median: 6100 },
    intern: { calls: 1, errors: 0, ms_median: 14000 },
    keenable: { calls: 3, errors: 0, ms_median: 1800 },
    deepinfra: { calls: 4, errors: 0, ms_median: 910 },
    adobe: { calls: 0, note: 'Firefly avatars + Express slides (offline)' },
  },
  verdicts: 4,
  cost_usd_est: 0.009,
}

export function mockLedger(): Ledger {
  return structuredClone(ledger)
}

function bump(tool: string, n = 1) {
  const t = ledger.tools[tool]
  if (t) t.calls += n
}

const LABELS: Record<AgentId, string> = {
  budget: 'Budget You', goals: 'Goals You', owned: 'Already-Own-It You', deal: 'Deal You',
}

type VoteSpec = Omit<VoteEvent, 'type' | 'label' | 'ms' | 'model' | 'stance'>

const BANK = { doc: 'bank_statement.pdf', doc_label: 'Bank statement', page: 1 }
const MEMO = { doc: 'rules_memo.m4a', doc_label: 'Voice memo · rules', page: null }
const KEEN = { doc: 'keenable:search', doc_label: 'Keenable live search', page: null }

interface Scenario {
  perceive: { item_name: string; category: string; category_p: number; price_bucket: string; price: number }
  votes: VoteSpec[]
  veto: { p: number; fired: boolean; reason: string }
  pool: { p: number }
  negotiation?: VerdictStreamEvent & { type: 'negotiation' }
  verdict: VerdictStreamEvent & { type: 'verdict' }
  sentence: string
}

const SCENARIOS: Record<DemoItemId, Scenario> = {
  shoes: {
    perceive: { item_name: 'ASICS Gel-Nimbus 27 Running Shoes', category: 'running_gear', category_p: 0.97, price_bucket: '100_199', price: 109.95 },
    votes: [
      { agent: 'budget', p_regret: 0.06, stake: 3.1, headline: 'Fits: $425 free → $315 left before payday',
        citation: { ...BANK, quote: 'Available balance (Nov 14) $2,480.00', bbox: null, crop_url: null }, cite_p: 0.93 },
      { agent: 'goals', p_regret: 0.14, stake: 4.2, headline: 'Running gear is exempt from your gadget rule',
        citation: { ...MEMO, quote: '“No gadgets over $200 before Japan. Running gear is exempt.”', bbox: null, crop_url: null }, cite_p: 0.95 },
      { agent: 'owned', p_regret: 0.11, stake: 2.0, headline: 'No running shoes on any receipt this year',
        citation: { doc: 'receipt_email.eml', doc_label: 'Receipt email', page: null, quote: 'Order #4471 · Yoga mat · $38.00', bbox: null, crop_url: null }, cite_p: 0.88 },
      { agent: 'deal', p_regret: 0.29, stake: 1.6, headline: 'Good price — typically $160 elsewhere',
        citation: { ...KEEN, quote: 'runrepeat.com — Gel-Nimbus 27, typical price $160', bbox: null, crop_url: null }, cite_p: 0.81 },
    ],
    veto: { p: 0.02, fired: false, reason: 'All scheduled bills stay covered' },
    pool: { p: 0.14 },
    verdict: { type: 'verdict', band: 'buy', title: 'Buy it', p: 0.14, condition: null,
      tally: { buy: 4, wait: 0 }, price_terms: { hours_of_work: 2.6, japan_slip_days: 12, pct_free_cash: 26 }, total_ms: 684 },
    sentence: 'Running gear is exempt from your own rule and it fits before payday — go run.',
  },
  headphones: {
    perceive: { item_name: 'Sony WH-1000XM6 Headphones', category: 'headphones', category_p: 0.99, price_bucket: '200_399', price: 349 },
    votes: [
      { agent: 'budget', p_regret: 0.21, stake: 2.3, headline: 'Fits in $425 free cash; $76 left before payday',
        citation: { ...BANK, quote: 'Available balance (Nov 14) $2,480.00', bbox: [0.72, 0.25, 0.8, 0.27], crop_url: null }, cite_p: 0.91 },
      { agent: 'goals', p_regret: 0.97, stake: 7.7, headline: 'Breaks your rule: no gadgets over $200 before Japan',
        citation: { ...MEMO, quote: '“No gadgets over $200 before Japan. Running gear is exempt.”', bbox: null, crop_url: null }, cite_p: 0.96 },
      { agent: 'owned', p_regret: 0.78, stake: 5.3, headline: 'You bought Pulse Pro earbuds in March for $179',
        citation: { doc: 'paper_receipt.jpg', doc_label: 'Paper receipt', page: 1, quote: 'PULSE PRO EARBUDS · GRAPHITE · 179.00', bbox: [0.12, 0.33, 0.65, 0.43], crop_url: '/mock_crops/earbuds.png' }, cite_p: 0.94 },
      { agent: 'deal', p_regret: 0.08, stake: 4.6, headline: 'Good price — typically $378 elsewhere',
        citation: { ...KEEN, quote: 'techradar.com — WH-1000XM6 just hit an all-time low', bbox: null, crop_url: null }, cite_p: 0.77 },
    ],
    veto: { p: 0.18, fired: false, reason: 'Rent $1,850 on Nov 20 stays covered' },
    pool: { p: 0.83 },
    negotiation: {
      type: 'negotiation',
      offers: [
        { id: 'wait_payday', label: 'Wait until payday (11/27)', amount: null },
        { id: 'skip_takeout_2', label: 'Skip two takeout orders ($54)', amount: 54.44 },
        { id: 'resell_earbuds', label: 'Resell the March earbuds (≈ +$90)', amount: 90 },
        { id: 'top_up_japan', label: 'Top up Japan fund by $149', amount: 149 },
        { id: 'resell_and_topup', label: 'Resell the earbuds (≈ +$90) AND put $149 into the Japan fund', amount: 239 },
      ],
      picks: [
        { agent: 'goals', offer_id: 'resell_and_topup', p_before: 0.97, p_after: 0.04 },
        { agent: 'owned', offer_id: 'resell_and_topup', p_before: 0.78, p_after: 0.05 },
      ],
      chosen: { id: 'resell_and_topup', label: 'Resell the earbuds (≈ +$90) AND put $149 into the Japan fund', amount: 239, p_after: 0.04 },
      pooled_by_offer: { wait_payday: 0.52, skip_takeout_2: 0.92, resell_earbuds: 0.46, top_up_japan: 0.37, resell_and_topup: 0.04 },
      ms: 360,
    },
    verdict: { type: 'verdict', band: 'buy_with_condition', title: 'Buy — with a condition', p: 0.04,
      condition: 'Resell the earbuds (≈ +$90) AND put $149 into the Japan fund', tally: { buy: 2, wait: 2 },
      price_terms: { hours_of_work: 8.3, japan_slip_days: 38, pct_free_cash: 82 }, total_ms: 712 },
    sentence: 'Good price and it fits your budget — buy it if you resell the earbuds and move $149 into the Japan fund.',
  },
  macmini: {
    perceive: { item_name: 'Apple Mac mini (M5, 16GB)', category: 'computer', category_p: 0.98, price_bucket: '400_799', price: 599 },
    votes: [
      { agent: 'budget', p_regret: 0.94, stake: 9.2, headline: '$599 is $174 over your $425 free cash',
        citation: { doc: 'pay_stub.jpg', doc_label: 'Pay stub', page: 1, quote: 'Next pay date · Nov 27, 2026', bbox: [0.08, 0.37, 0.46, 0.43], crop_url: '/mock_crops/payday.png' }, cite_p: 0.97 },
      { agent: 'goals', p_regret: 0.81, stake: 6.8, headline: 'Slips Japan by 64 days and breaks your $200 rule',
        citation: { ...MEMO, quote: '“No gadgets over $200 before Japan. Running gear is exempt.”', bbox: null, crop_url: null }, cite_p: 0.95 },
      { agent: 'owned', p_regret: 0.33, stake: 2.1, headline: 'No desktop computer on any receipt',
        citation: { doc: 'receipt_email.eml', doc_label: 'Receipt email', page: null, quote: 'Order #4471 · Yoga mat · $38.00', bbox: null, crop_url: null }, cite_p: 0.84 },
      { agent: 'deal', p_regret: 0.61, stake: 3.0, headline: 'Education + Black Friday pricing drops it to ~$499',
        citation: { ...KEEN, quote: 'apple.com/us-edu — Mac mini from $499', bbox: null, crop_url: null }, cite_p: 0.8 },
    ],
    veto: { p: 0.959, fired: true, reason: 'Rent $1,850 on Nov 20 becomes unpayable' },
    pool: { p: 0.86 },
    verdict: { type: 'verdict', band: 'wait', title: 'Wait — until payday', p: 0.959,
      condition: 'Wait until payday (Nov 27)', tally: { buy: 1, wait: 3 },
      price_terms: { hours_of_work: 14.3, japan_slip_days: 64, pct_free_cash: 141 }, total_ms: 731 },
    sentence: 'Buying this today makes Friday’s rent bounce — your budget self is vetoing it until the Nov 27 paycheck lands.',
  },
}

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException('aborted', 'AbortError'))
    const t = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => { clearTimeout(t); reject(new DOMException('aborted', 'AbortError')) }, { once: true })
  })
}

const rand = (a: number, b: number) => Math.round(a + Math.random() * (b - a))

export async function* mockVerdict(req: VerdictRequest, signal: AbortSignal): AsyncGenerator<VerdictStreamEvent> {
  const id: DemoItemId = req.demo_item ?? 'headphones'
  const sc = SCENARIOS[id]
  const t0 = performance.now()

  yield { type: 'perceive_start' }
  const perceiveMs = rand(260, 340)
  await sleep(perceiveMs, signal)
  bump('drex'); if (!req.price) bump('ndi')
  const manual = req.price != null && req.price > 0
  yield {
    type: 'perceive', ...sc.perceive,
    item_name: req.item_name || sc.perceive.item_name,
    price: manual ? req.price : sc.perceive.price,
    price_source: manual ? 'manual' : req.demo_item ? 'cache' : 'ndi',
    ms: perceiveMs,
  }

  yield { type: 'council_start', agents: ['budget', 'goals', 'owned', 'deal'] }
  const tCouncil = performance.now()
  const timed = sc.votes.map((v) => ({ v, ms: rand(240, 410) })).sort((a, b) => a.ms - b.ms)
  let elapsed = 0
  for (const { v, ms } of timed) {
    await sleep(ms - elapsed, signal)
    elapsed = ms
    bump('drex', 2)
    if (v.agent === 'deal') bump('keenable')
    yield {
      type: 'vote', ...v, label: LABELS[v.agent],
      stance: v.p_regret < 0.5 ? 'buy' : 'wait',
      model: v.agent === 'budget' && id === 'macmini' ? 'drex-max-v1.1' : 'drex-v2.0', ms,
    }
  }

  await sleep(60, signal)
  bump('drex')
  yield { type: 'veto', agent: 'budget', threshold: 0.93, ...sc.veto }
  const weights = Object.fromEntries(sc.votes.map((v) => [v.agent, v.stake]))
  const band = sc.veto.fired ? 'wait' : sc.pool.p < 0.35 ? 'buy' : sc.pool.p <= 0.65 ? 'buy_with_condition' : 'wait'
  yield { type: 'pool', p: sc.pool.p, band, weights }

  if (sc.negotiation) {
    await sleep(sc.negotiation.ms, signal)
    bump('drex', sc.negotiation.picks.length)
    yield sc.negotiation
  }

  await sleep(120, signal)
  const now = performance.now()
  yield {
    ...sc.verdict, total_ms: Math.round(now - t0), council_ms: Math.round(now - tCouncil),
    p_round_one: sc.pool.p, veto: sc.veto.fired,
    item: { name: sc.perceive.item_name, price: manual ? req.price : sc.perceive.price, category: sc.perceive.category },
  }

  await sleep(rand(500, 800), signal)
  bump('deepinfra')
  ledger.verdicts += 1
  ledger.cost_usd_est = +(ledger.cost_usd_est + 0.0021).toFixed(4)
  yield { type: 'sentence', text: sc.sentence, source: 'deepinfra' }
  yield { type: 'done' }
}
