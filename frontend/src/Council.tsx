import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AGENTS, type AgentId, type Citation, type Pick, type VetoEvent, type VoteEvent } from './api'
import type { RunState } from './App'

export const AGENT_META: Record<AgentId, { label: string; mono: string; role: string }> = {
  budget: { label: 'Budget You', mono: 'B', role: 'bank statement · pay stub' },
  goals: { label: 'Goals You', mono: 'G', role: 'savings tracker · rules memo' },
  owned: { label: 'Already-Own-It You', mono: 'O', role: 'receipts' },
  deal: { label: 'Deal You', mono: 'D', role: 'live price search' },
}

export default function Council({ state }: { state: RunState }) {
  const waiting = state.phase === 'council' || state.phase === 'perceiving'
  const neg = state.negotiation
  return (
    <div className="council">
      {AGENTS.map((a) => (
        <SelfCard
          key={`${a}-${state.runId}`}
          agent={a}
          vote={state.votes[a]}
          waiting={waiting && !state.votes[a]}
          thinking={state.phase === 'council' && !state.votes[a]}
          veto={a === 'budget' ? state.veto : undefined}
          pick={neg?.picks.find((p) => p.agent === a)}
          offerLabel={(id) => neg?.offers.find((o) => o.id === id)?.label ?? id}
        />
      ))}
    </div>
  )
}

interface CardProps {
  agent: AgentId
  vote?: VoteEvent
  waiting: boolean
  thinking: boolean
  veto?: VetoEvent
  pick?: Pick
  offerLabel: (id: string) => string
}

function SelfCard({ agent, vote, thinking, veto, pick, offerLabel }: CardProps) {
  const meta = AGENT_META[agent]
  const lit = !!vote
  const p = pick ? pick.p_after : vote?.p_regret
  const stance = p != null ? (p < 0.5 ? 'buy' : 'wait') : undefined
  return (
    <motion.article
      className={`card card-${agent} ${lit ? 'lit' : ''} ${thinking ? 'thinking' : ''}`}
      style={{ ['--accent' as string]: `var(--c-${agent})` }}
      initial={false}
      animate={lit ? { scale: [0.98, 1.015, 1] } : { scale: 1 }}
      transition={{ duration: 0.45 }}
    >
      <header className="card-head">
        <Avatar agent={agent} />
        <div className="card-who">
          <div className="card-label">{vote?.label ?? meta.label}</div>
          <div className="card-role">{meta.role}</div>
        </div>
        <AnimatePresence>
          {pick && (
            <motion.span
              className="offer-landed"
              title={offerLabel(pick.offer_id)}
              initial={{ opacity: 0, y: -40, scale: 0.7 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.55 }}
            >
              <span className="offer-landed-label">with offer</span>
              <span className="offer-landed-p">{pick.p_before.toFixed(2)} → <b>{pick.p_after.toFixed(2)}</b></span>
            </motion.span>
          )}
        </AnimatePresence>
        <AnimatePresence>
          {stance && (
            <motion.span key={stance} className={`pill pill-${stance}`} initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', stiffness: 500, damping: 22 }}>
              {stance === 'buy' ? '✓ BUY' : '✕ WAIT'}
            </motion.span>
          )}
        </AnimatePresence>
      </header>

      {vote ? (
        <motion.div className="card-body" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
          <div className="headline">{vote.headline}</div>
          <div className="card-stats">
            <RegretBar p={vote.p_regret} after={pick?.p_after} />
            <Stake stake={vote.stake} />
          </div>
          <CitationView c={vote.citation} citeP={vote.cite_p} model={vote.model} ms={vote.ms} />
        </motion.div>
      ) : (
        <div className="card-body card-empty">
          {thinking ? <span className="thinking-dots">Thinking<span>.</span><span>.</span><span>.</span></span> : <span className="muted">Waiting for an item</span>}
        </div>
      )}

      <AnimatePresence>
        {veto?.fired && (
          <motion.div
            className="veto-stamp"
            initial={{ scale: 3, opacity: 0, rotate: -24 }}
            animate={{ scale: 1, opacity: 1, rotate: -12 }}
            transition={{ type: 'spring', stiffness: 420, damping: 16, delay: 0.1 }}
          >
            <span className="veto-word">VETO</span>
            <span className="veto-reason">{veto.reason}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  )
}

function Avatar({ agent }: { agent: AgentId }) {
  const [failed, setFailed] = useState(false)
  return failed ? (
    <div className="avatar avatar-mono" aria-hidden>{AGENT_META[agent].mono}</div>
  ) : (
    <img className="avatar" src={`/avatars/${agent}.png`} alt="" onError={() => setFailed(true)} />
  )
}

function RegretBar({ p, after }: { p: number; after?: number }) {
  const shown = after ?? p
  return (
    <div className="regret" aria-label={`Probability of regret ${shown.toFixed(2)}`}>
      <span className="regret-label muted">regret</span>
      <div className="regret-track">
        <span className="regret-tick" style={{ left: '50%' }} />
        <motion.span
          className="regret-fill"
          initial={{ width: '0%' }}
          animate={{ width: `${shown * 100}%` }}
          transition={{ type: 'spring', stiffness: 140, damping: 20, delay: after != null ? 0.7 : 0 }}
        />
        {after != null && <span className="regret-ghost" style={{ left: `${p * 100}%` }} title={`before ${p.toFixed(2)}`} />}
      </div>
      <span className="regret-value">{shown.toFixed(2)}</span>
    </div>
  )
}

function Stake({ stake }: { stake: number }) {
  const n = Math.round(stake)
  return (
    <span className="stake" aria-label={`Stake ${stake.toFixed(1)} of 10`}>
      <span className="muted">stake</span>
      <span className="stake-dots">
        {Array.from({ length: 10 }, (_, i) => <span key={i} className={`dot ${i < n ? 'on' : ''}`} />)}
      </span>
      <span className="stake-num">{stake.toFixed(1)}</span>
    </span>
  )
}

function CitationView({ c, citeP, model, ms }: { c: Citation; citeP?: number; model: string; ms: number }) {
  const [imgFailed, setImgFailed] = useState(false)
  const hasImg = c.crop_url && !imgFailed
  return (
    <div className="citation">
      <div className="cite-src">
        <span className="cite-icon" aria-hidden>❝</span>
        <span className="cite-doc">{c.doc_label}{c.page != null ? ` · p.${c.page}` : ''}</span>
        <span className="meta">{citeP != null ? `cite p ${citeP.toFixed(2)} · ` : ''}{model} · {ms} ms</span>
      </div>
      <motion.div
        className={`paper ${hasImg ? 'paper-img' : ''}`}
        initial={{ opacity: 0, rotate: -4, y: 10 }}
        animate={{ opacity: 1, rotate: -1.2, y: 0 }}
        transition={{ type: 'spring', stiffness: 220, damping: 18, delay: 0.15 }}
      >
        {hasImg ? (
          <>
            <img src={c.crop_url!} alt="" onError={() => setImgFailed(true)} />
            <span className="paper-caption">{c.quote}</span>
          </>
        ) : (
          <span className="paper-quote">{c.quote}</span>
        )}
      </motion.div>
    </div>
  )
}
