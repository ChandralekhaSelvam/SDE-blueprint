import { useMemo, useState } from 'react'
import { api } from '../lib/api'
import { ARCHETYPE_COLOR } from './MeshGraph'
import type { AgentSpec, Blueprint, ScoredTask } from '../lib/types'

const BAND_LABEL: Record<string, string> = {
  full_agent: 'Full agent',
  hitl: 'Human in the loop',
  human_only: 'Human only',
}

const money = (v: number) => (v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`)

/* ------------------------------------------------------------------ catalog */

export function Catalog({ bp, onSelect }: { bp: Blueprint; onSelect: (id: string) => void }) {
  return (
    <div className="card">
      <div className="card-head">
        <h2 style={{ margin: 0 }}>Agent catalog</h2>
        <span className="muted" style={{ fontSize: 12.5 }}>
          {bp.agents.length} agents covering {bp.task_count} source activities
        </span>
        <span className="spacer" />
        <a className="btn small" href={api.blueprintUrl(bp.run_id)}>Download JSON</a>
      </div>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Agent</th><th>Archetype</th><th className="num">Tasks</th>
              <th className="num">Hours now</th><th className="num">Hours after</th>
              <th className="num">Automation</th><th>Risk</th><th>Model</th>
            </tr>
          </thead>
          <tbody>
            {bp.agents.map((a) => (
              <tr key={a.id} onClick={() => onSelect(a.id)} style={{ cursor: 'pointer' }}>
                <td>
                  <span className="dot" style={{ background: ARCHETYPE_COLOR[a.archetype] }} />
                  <strong>{a.name}</strong>
                  <div className="muted mono" style={{ fontSize: 11 }}>{a.id}</div>
                </td>
                <td className="dim">{a.archetype}</td>
                <td className="num">{a.estimate.source_task_count}</td>
                <td className="num">{a.estimate.annual_hours_today.toLocaleString()}</td>
                <td className="num">{a.estimate.annual_hours_after.toLocaleString()}</td>
                <td className="num"><strong>{a.estimate.automation_pct}%</strong></td>
                <td className="dim">{a.risk_tier}</td>
                <td className="dim mono" style={{ fontSize: 11.5 }}>{a.model_tier}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------- gates */

export function Gates({ bp }: { bp: Blueprint }) {
  const byId = Object.fromEntries(bp.agents.map((a) => [a.id, a]))
  if (!bp.gates.length) {
    return (
      <div className="card card-pad">
        <h2>No human gates required</h2>
        <p className="dim">
          Every activity in this inventory cleared the autonomous band and no policy override fired.
          That is unusual. Check the inventory carries sensitivity flags before presenting this result.
        </p>
      </div>
    )
  }
  return (
    <div className="stack">
      {bp.gates.map((g) => {
        const agent = byId[g.before_agent]
        return (
          <div className="card card-pad" key={g.id}>
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="mono muted">{g.id}</span>
              <strong>Before {agent?.name ?? g.before_agent}</strong>
              <span className="pill">{g.reviewer_role}</span>
              <span className="spacer" />
              <span className="muted" style={{ fontSize: 12.5 }}>
                {g.task_count} activities · about {g.est_review_minutes} review minutes a month
              </span>
            </div>
            <p className="dim" style={{ marginBottom: 10 }}>{g.reason}</p>
            <h3>The run halts here when</h3>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }} className="dim">
              {g.triggers.map((t) => <li key={t}>{t}</li>)}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------- traceability */

export function Traceability({ bp, onSelectTask }: { bp: Blueprint; onSelectTask: (id: string) => void }) {
  const [q, setQ] = useState('')
  const [band, setBand] = useState('all')

  const rows = useMemo(() => bp.traceability.filter((r) => {
    if (band !== 'all' && r.band !== band) return false
    if (!q) return true
    const hay = `${r.l4_code} ${r.l4_name} ${r.agent_name}`.toLowerCase()
    return hay.includes(q.toLowerCase())
  }), [bp, q, band])

  return (
    <div className="card">
      <div className="card-head">
        <h2 style={{ margin: 0 }}>Traceability</h2>
        <span className="muted" style={{ fontSize: 12.5 }}>{rows.length} of {bp.traceability.length} rows</span>
        <span className="spacer" />
        <input placeholder="Filter activities" value={q} onChange={(e) => setQ(e.target.value)}
               style={{ padding: '5px 10px', border: '1px solid var(--line-2)', borderRadius: 6, background: 'var(--surface)', color: 'var(--ink)', fontSize: 13 }} />
        <select value={band} onChange={(e) => setBand(e.target.value)}
                style={{ padding: '5px 8px', border: '1px solid var(--line-2)', borderRadius: 6, background: 'var(--surface)', color: 'var(--ink)', fontSize: 13 }}>
          <option value="all">Every band</option>
          <option value="full_agent">Full agent</option>
          <option value="hitl">Human in the loop</option>
          <option value="human_only">Human only</option>
        </select>
        <a className="btn small" href={api.traceabilityUrl(bp.run_id)}>Download CSV</a>
      </div>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>L4</th><th>Activity</th><th>Agent</th><th>Gate</th>
              <th className="num">Score</th><th>Band</th><th>Resolved by</th><th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.task_id} onClick={() => onSelectTask(r.task_id)} style={{ cursor: 'pointer' }}>
                <td className="mono muted">{r.l4_code}</td>
                <td>{r.l4_name}</td>
                <td className="dim">{r.agent_name}</td>
                <td className="mono muted">{r.gate_id ?? '—'}</td>
                <td className="num"><strong>{r.score}</strong></td>
                <td><span className={`band ${r.band}`}>{BAND_LABEL[r.band]}</span></td>
                <td className="dim" style={{ fontSize: 12 }}>{r.resolution.replace('_', ' ')}</td>
                <td className="muted" style={{ fontSize: 11.5 }}>
                  {r.evidence.map((e) => e.source.split('/').pop()).slice(0, 2).join(', ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------------- cost */

export function Cost({ bp }: { bp: Blueprint }) {
  const c = bp.cost
  const res = c.by_resolution
  const total = Math.max(1, Object.values(res).reduce((a, b) => a + b, 0))
  const segments = [
    { key: 'deterministic', label: 'resolved by arithmetic, no model call', colour: '#2f6feb' },
    { key: 'cache', label: 'served from the task cache', colour: '#7a5af8' },
    { key: 'small_model', label: 'small model', colour: '#0e9f6e' },
    { key: 'large_model', label: 'larger model', colour: '#d97706' },
  ]

  return (
    <div className="stack">
      <div className="card card-pad">
        <div className="stats" style={{ marginBottom: 18 }}>
          <div className="stat"><div className="v">{money(c.total_cost_usd)}</div><div className="k">this run</div></div>
          <div className="stat"><div className="v muted">{money(c.naive_cost_usd)}</div><div className="k">one call per activity</div></div>
          <div className="stat"><div className="v">{c.saved_pct}%</div><div className="k">avoided</div></div>
          <div className="stat"><div className="v">{money(c.cost_per_1k_tasks)}</div><div className="k">per 1,000 activities</div></div>
          <div className="stat"><div className="v">{c.total_tokens.toLocaleString()}</div><div className="k">tokens</div></div>
          <div className="stat"><div className="v">{c.cache_hit_rate}%</div><div className="k">cache hits</div></div>
        </div>

        <h3>How {bp.task_count} activities were resolved</h3>
        <div className="bar">
          {segments.map((s) => (res[s.key] ? (
            <div key={s.key} style={{ flex: res[s.key], background: s.colour }} title={`${res[s.key]} ${s.label}`} />
          ) : null))}
        </div>
        <div className="legend" style={{ borderTop: 0, marginTop: 8 }}>
          {segments.filter((s) => res[s.key]).map((s) => (
            <span key={s.key}><span className="dot" style={{ background: s.colour }} />{res[s.key]} {s.label}</span>
          ))}
        </div>
        <p className="dim" style={{ marginTop: 12, fontSize: 13 }}>
          {c.llm_calls_avoided} of {bp.task_count} activities never reached a model. The seven weighted
          dimensions are arithmetic over features, so a model is consulted only where the deterministic
          result sits near a band boundary or the source row is too thin to be confident.
        </p>
      </div>

      {c.by_stage.length > 0 && (
        <div className="card">
          <div className="card-head"><h2 style={{ margin: 0 }}>Routing ledger</h2></div>
          <table>
            <thead><tr><th>Stage</th><th>Model</th><th>Tier</th><th className="num">Calls</th><th className="num">Tokens</th><th className="num">Cost</th></tr></thead>
            <tbody>
              {c.by_stage.map((s, i) => (
                <tr key={i}>
                  <td>{s.stage}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{s.model}</td>
                  <td className="dim">{s.tier}</td>
                  <td className="num">{s.calls}</td>
                  <td className="num">{s.tokens.toLocaleString()}</td>
                  <td className="num">{money(s.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Bridge bp={bp} />
    </div>
  )
}

/* ------------------------------------------------------------------- bridge */

export function Bridge({ bp }: { bp: Blueprint }) {
  const b = bp.bridge
  const W = 620
  const Hpx = 190
  const scale = Hpx / Math.max(b.fte_today, 1)
  const y = (v: number) => Hpx - v * scale
  const colours = ['#2f6feb', '#7a5af8', '#d97706']
  const cols = b.steps.length + 2
  const bw = Math.min(88, (W - 40) / cols - 16)
  const gap = (W - 20 - cols * bw) / Math.max(cols - 1, 1)
  const xAt = (i: number) => 10 + i * (bw + gap)

  return (
    <div className="card card-pad">
      <h2>Effort bridge</h2>
      <p className="dim" style={{ fontSize: 13 }}>
        Weighted by hours, not by task count. A small number of high-volume activities carries most of
        the effort, which is why the share of hours removed runs well ahead of the share of tasks.
      </p>
      <svg viewBox={`0 0 ${W} ${Hpx + 46}`} className="canvas" role="img"
           aria-label={`Bridge from ${b.fte_today} to ${b.fte_after} FTE`}>
        <line x1="0" y1={Hpx} x2={W} y2={Hpx} stroke="var(--line)" />
        <rect x={xAt(0)} y={y(b.fte_today)} width={bw} height={b.fte_today * scale} rx={4}
              fill="var(--surface-sunk)" stroke="var(--line-2)" strokeWidth="1.5" />
        <text x={xAt(0) + bw / 2} y={y(b.fte_today) - 6} textAnchor="middle" className="node-meta" fill="var(--ink)">{b.fte_today}</text>
        <text x={xAt(0) + bw / 2} y={Hpx + 16} textAnchor="middle" style={{ fontSize: 11 }} fill="var(--ink-2)">Today</text>

        {b.steps.map((s, i) => {
          const top = y(s.from)
          const height = Math.max(2, (s.from - s.to) * scale)
          return (
            <g key={s.band}>
              <rect x={xAt(i + 1)} y={top} width={bw} height={height} rx={4} fill={colours[i]} opacity="0.9" />
              <text x={xAt(i + 1) + bw / 2} y={top - 6} textAnchor="middle" className="node-meta" fill="var(--ink)">−{s.fte_removed}</text>
              <text x={xAt(i + 1) + bw / 2} y={Hpx + 16} textAnchor="middle" style={{ fontSize: 11 }} fill="var(--ink-2)">
                {s.label.split(' ')[0]}
              </text>
              <text x={xAt(i + 1) + bw / 2} y={Hpx + 30} textAnchor="middle" style={{ fontSize: 10.5 }} fill="var(--ink-3)">
                {s.share_of_hours}% hrs · {Math.round(s.residual * 100)}% left
              </text>
            </g>
          )
        })}

        <rect x={xAt(cols - 1)} y={y(b.fte_after)} width={bw} height={Math.max(2, b.fte_after * scale)} rx={4}
              fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.8" />
        <text x={xAt(cols - 1) + bw / 2} y={y(b.fte_after) - 6} textAnchor="middle" className="node-meta" fill="var(--ink)">{b.fte_after}</text>
        <text x={xAt(cols - 1) + bw / 2} y={Hpx + 16} textAnchor="middle" style={{ fontSize: 11 }} fill="var(--ink-2)">Target</text>
      </svg>
      <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>
        Residual factors are assumptions, not findings. Human-in-the-loop work is usually modelled as
        zero saving; here a reviewed activity is assumed to drop to {Math.round((b.residuals.hitl ?? 0.15) * 100)}%
        of its original handling time, because approving a draft is faster than producing one.
        The system scores activities, never people.
      </p>
    </div>
  )
}

/* ------------------------------------------------------------------- drawer */

export function AgentDrawer({ bp, agent, onClose }: { bp: Blueprint; agent: AgentSpec; onClose: () => void }) {
  const tasks = bp.scored_tasks.filter((t) => agent.source_task_ids.includes(t.task.id))
  const deps = bp.dependencies.filter((d) => d.source === agent.id || d.target === agent.id)
  const gate = bp.gates.find((g) => g.before_agent === agent.id)

  return (
    <div className="drawer-wrap">
      <button className="scrim" onClick={onClose} aria-label="Close" />
      <aside className="drawer">
        <div className="row" style={{ marginBottom: 12 }}>
          <span className="dot" style={{ background: ARCHETYPE_COLOR[agent.archetype] }} />
          <h2 style={{ margin: 0 }}>{agent.name}</h2>
          <span className="spacer" />
          <button className="btn small" onClick={onClose}>Close</button>
        </div>
        <p className="dim">{agent.purpose}</p>

        <h3>Specification</h3>
        <dl className="kv" style={{ marginBottom: 16 }}>
          <dt>Archetype</dt><dd>{agent.archetype}</dd>
          <dt>Model tier</dt><dd>{agent.model_tier}</dd>
          <dt>Risk tier</dt><dd>{agent.risk_tier}</dd>
          <dt>Written by</dt><dd>{agent.generated_by === 'model' ? 'model' : 'template, no model call'}</dd>
          <dt>Tools</dt><dd>{agent.tools.join(', ')}</dd>
          <dt>Guardrails</dt><dd>{agent.guardrails.join(', ')}</dd>
          <dt>Contract</dt><dd className="mono" style={{ fontSize: 11.5 }}>{agent.io_contract.in} → {agent.io_contract.out}</dd>
        </dl>

        <h3>Automation estimate</h3>
        <dl className="kv" style={{ marginBottom: 16 }}>
          <dt>Source activities</dt><dd>{agent.estimate.source_task_count}</dd>
          <dt>Annual hours</dt><dd>{agent.estimate.annual_hours_today.toLocaleString()} → {agent.estimate.annual_hours_after.toLocaleString()}</dd>
          <dt>FTE</dt><dd>{agent.estimate.fte_today} → {agent.estimate.fte_after}</dd>
          <dt>Hours removed</dt><dd>{agent.estimate.automation_pct}%</dd>
          <dt>Band split</dt><dd>{Object.entries(agent.estimate.band_split).filter(([, v]) => v).map(([k, v]) => `${v} ${BAND_LABEL[k].toLowerCase()}`).join(', ')}</dd>
        </dl>

        {gate && (
          <>
            <h3>Human gate</h3>
            <p className="dim" style={{ fontSize: 13 }}>{gate.reason}</p>
          </>
        )}

        {deps.length > 0 && (
          <>
            <h3>Dependencies</h3>
            {deps.map((d, i) => (
              <div className="evidence" key={i}>
                <strong>{d.source} → {d.target}</strong>
                <div className="muted">{d.payload}{d.carries_pii ? ', masked in transit' : ''}{d.cross_tower ? ', crosses process groups' : ''}</div>
              </div>
            ))}
          </>
        )}

        <h3 style={{ marginTop: 16 }}>Source activities</h3>
        <table>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.task.id}>
                <td className="mono muted" style={{ fontSize: 11 }}>{t.task.l4_code}</td>
                <td style={{ fontSize: 12.5 }}>{t.task.l4_name}</td>
                <td className="num">{t.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </aside>
    </div>
  )
}

export function TaskDrawer({ bp, task, onClose, onOverride }: {
  bp: Blueprint; task: ScoredTask; onClose: () => void
  onOverride: (taskId: string, band: string, reason: string) => Promise<void>
}) {
  const [band, setBand] = useState(task.band as string)
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  return (
    <div className="drawer-wrap">
      <button className="scrim" onClick={onClose} aria-label="Close" />
      <aside className="drawer">
        <div className="row" style={{ marginBottom: 4 }}>
          <span className="mono muted">{task.task.l4_code}</span>
          <span className="spacer" />
          <button className="btn small" onClick={onClose}>Close</button>
        </div>
        <h2>{task.task.l4_name}</h2>

        <div className="row" style={{ marginBottom: 12 }}>
          <span style={{ fontSize: 30, fontWeight: 600 }} className="mono">{task.score}</span>
          {task.overrides.length > 0 && (
            <span className="mono muted" style={{ fontSize: 16, textDecoration: 'line-through' }}>{task.raw_score}</span>
          )}
          <span className={`band ${task.band}`}>{BAND_LABEL[task.band]}</span>
          <span className="muted" style={{ fontSize: 12 }}>confidence {task.confidence}</span>
        </div>

        {task.overrides.map((o, i) => (
          <div className="notice" key={i} style={{ marginBottom: 10 }}>
            <strong>Capped at {o.cap} by the {o.rule} rule.</strong> {o.reason}
            <div className="muted mono" style={{ fontSize: 11, marginTop: 3 }}>{o.source}</div>
          </div>
        ))}

        <h3>Dimensions</h3>
        <div style={{ marginBottom: 16 }}>
          {task.dimensions.map((d) => (
            <div key={d.key} style={{ marginBottom: 7 }}>
              <div className="row" style={{ fontSize: 12, gap: 6 }}>
                <span style={{ flex: 1 }}>{d.label}</span>
                <span className="mono muted">{Math.round(d.raw)} × {d.weight.toFixed(2)}</span>
              </div>
              <div style={{ height: 4, background: 'var(--surface-sunk)', borderRadius: 2 }}>
                <div style={{ width: `${d.raw}%`, height: '100%', background: 'var(--extraction)', borderRadius: 2 }} />
              </div>
              <div className="muted" style={{ fontSize: 11 }}>{d.basis}</div>
            </div>
          ))}
        </div>

        <h3>Evidence</h3>
        {task.evidence.map((e, i) => (
          <div className={`evidence ${e.kind}`} key={i}>
            <strong>{e.label}</strong>
            <div className="dim">{e.detail}</div>
            <div className="muted mono" style={{ fontSize: 11 }}>{e.kind} · {e.source}</div>
          </div>
        ))}

        <h3 style={{ marginTop: 16 }}>Override this classification</h3>
        <p className="muted" style={{ fontSize: 12.5 }}>
          A reason is required. The change is attributed and written to the audit log.
        </p>
        <div className="row" style={{ marginBottom: 8 }}>
          <select value={band} onChange={(e) => setBand(e.target.value)}
                  style={{ padding: '6px 8px', border: '1px solid var(--line-2)', borderRadius: 6, background: 'var(--surface)', color: 'var(--ink)' }}>
            <option value="full_agent">Full agent</option>
            <option value="hitl">Human in the loop</option>
            <option value="human_only">Human only</option>
          </select>
          <input placeholder="Why are you changing this?" value={reason} onChange={(e) => setReason(e.target.value)}
                 style={{ flex: 1, minWidth: 160, padding: '6px 10px', border: '1px solid var(--line-2)', borderRadius: 6, background: 'var(--surface)', color: 'var(--ink)' }} />
        </div>
        {err && <div className="error" style={{ marginBottom: 8 }}>{err}</div>}
        <button className="btn" disabled={saving || !reason.trim()} onClick={async () => {
          setSaving(true); setErr(null)
          try { await onOverride(task.task.id, band, reason); onClose() }
          catch (e: any) { setErr(e.message) }
          finally { setSaving(false) }
        }}>Record the override</button>
      </aside>
    </div>
  )
}
