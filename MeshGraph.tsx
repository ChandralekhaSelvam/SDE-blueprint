import { useMemo, useState } from 'react'
import type { AgentDependency, AgentSpec, HumanGate } from '../lib/types'

export const ARCHETYPE_COLOR: Record<string, string> = {
  extraction: '#2f6feb',
  reasoning: '#7a5af8',
  generation: '#0e9f6e',
  monitoring: '#d97706',
  orchestration: '#64748b',
}

const ORDER = ['extraction', 'reasoning', 'generation', 'monitoring', 'orchestration']

const NODE_W = 138
const NODE_H = 62
const COL_GAP = 54
const ROW_GAP = 22

type Placed = { spec: AgentSpec; x: number; y: number }

/**
 * Sugiyama-lite layering. Column comes from archetype order, which is the fixed
 * grammar of the mesh, so the graph always reads left to right as extract,
 * reason, generate, monitor. Rows are packed within a column. This is stable
 * across runs, which matters: a client comparing two towers should see the same
 * shape move, not a different random layout.
 */
function layout(agents: AgentSpec[]) {
  const columns: AgentSpec[][] = ORDER.map((a) => agents.filter((s) => s.archetype === a)).filter((c) => c.length > 0)
  const placed: Placed[] = []
  const tallest = Math.max(1, ...columns.map((c) => c.length))

  columns.forEach((col, ci) => {
    const colHeight = col.length * NODE_H + (col.length - 1) * ROW_GAP
    const fullHeight = tallest * NODE_H + (tallest - 1) * ROW_GAP
    const top = (fullHeight - colHeight) / 2
    col.forEach((spec, ri) => {
      placed.push({ spec, x: 8 + ci * (NODE_W + COL_GAP), y: 8 + top + ri * (NODE_H + ROW_GAP) })
    })
  })

  const width = 16 + columns.length * NODE_W + (columns.length - 1) * COL_GAP
  const height = 16 + tallest * NODE_H + (tallest - 1) * ROW_GAP
  return { placed, width, height: Math.max(height, 150) }
}

interface Props {
  agents: AgentSpec[]
  dependencies: AgentDependency[]
  gates: HumanGate[]
  selected: string | null
  onSelect: (id: string | null) => void
  overlay: 'archetype' | 'automation' | 'risk' | 'priority'
  simulating: boolean
}

export function MeshGraph({ agents, dependencies, gates, selected, onSelect, overlay, simulating }: Props) {
  const [hoverEdge, setHoverEdge] = useState<AgentDependency | null>(null)
  const { placed, width, height } = useMemo(() => layout(agents), [agents])
  const byId = useMemo(() => Object.fromEntries(placed.map((p) => [p.spec.id, p])), [placed])
  const gateFor = useMemo(() => Object.fromEntries(gates.map((g) => [g.before_agent, g])), [gates])

  if (!agents.length) return <p className="muted">No agents were generated for this inventory.</p>

  const shade = (spec: AgentSpec) => {
    if (overlay === 'archetype') return ARCHETYPE_COLOR[spec.archetype]
    if (overlay === 'risk') return { low: '#0e9f6e', medium: '#d97706', high: '#dc2626' }[spec.risk_tier] ?? '#64748b'
    if (overlay === 'automation') {
      const p = spec.estimate.automation_pct
      return p >= 70 ? '#0e9f6e' : p >= 40 ? '#d97706' : '#64748b'
    }
    // AI priority: value over effort, sized rather than hued.
    return '#2f6feb'
  }

  const priority = (spec: AgentSpec) => {
    const value = spec.estimate.hours_removed
    const max = Math.max(...agents.map((a) => a.estimate.hours_removed), 1)
    return 1 + Math.round((value / max) * 9)
  }

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="canvas" role="img"
           aria-label={`Agent mesh: ${agents.length} agents, ${dependencies.length} dependencies, ${gates.length} human gates`}>
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0,1 L7,4 L0,7" fill="none" stroke="var(--line-2)" strokeWidth="1.3" />
          </marker>
        </defs>

        {dependencies.map((dep, i) => {
          const a = byId[dep.source]
          const b = byId[dep.target]
          if (!a || !b) return null
          const x1 = a.x + NODE_W
          const y1 = a.y + NODE_H / 2
          const x2 = b.x
          const y2 = b.y + NODE_H / 2
          const mid = (x1 + x2) / 2
          const active = hoverEdge === dep
          return (
            <path
              key={i}
              d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
              className={`edge ${simulating ? 'edge-flow' : ''}`}
              stroke={active ? 'var(--accent)' : 'var(--line-2)'}
              strokeWidth={active ? 2 : 1.3}
              strokeDasharray={dep.cross_tower && !simulating ? '4 4' : undefined}
              markerEnd="url(#arrow)"
              onMouseEnter={() => setHoverEdge(dep)}
              onMouseLeave={() => setHoverEdge(null)}
              style={{ cursor: 'pointer' }}
            />
          )
        })}

        {placed.map(({ spec, x, y }, i) => {
          const colour = shade(spec)
          const isSel = selected === spec.id
          const gate = gateFor[spec.id]
          const size = overlay === 'priority' ? 1.5 + priority(spec) * 0.28 : isSel ? 2.5 : 1.8
          return (
            <g key={spec.id} className="node node-enter" style={{ animationDelay: `${i * 45}ms` }}
               onClick={() => onSelect(isSel ? null : spec.id)} role="button" tabIndex={0}
               onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(isSel ? null : spec.id) } }}
               aria-label={`${spec.name}, ${spec.estimate.source_task_count} source tasks, ${spec.estimate.automation_pct} percent automatable`}>
              <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={7}
                    fill="var(--surface)" stroke={colour} strokeWidth={size} />
              <text x={x + 11} y={y + 21} className="node-label" fill="var(--ink)">
                {spec.name.length > 21 ? `${spec.name.slice(0, 20)}…` : spec.name}
              </text>
              <text x={x + 11} y={y + 37} className="node-meta" fill="var(--ink-3)">
                {spec.id} · {spec.estimate.source_task_count} tasks
              </text>
              <text x={x + 11} y={y + 52} className="node-meta" fill="var(--ink-2)">
                {spec.estimate.automation_pct}% of hours
              </text>
              {gate && (
                <g aria-hidden="true">
                  <path d={`M${x - 15},${y + NODE_H / 2} l11,-11 l11,11 l-11,11 z`}
                        fill="var(--surface)" stroke="var(--gate)" strokeWidth="1.8" />
                  <title>{gate.reason}</title>
                </g>
              )}
            </g>
          )
        })}
      </svg>

      <div className="legend">
        {overlay === 'archetype' && ORDER.filter((a) => agents.some((s) => s.archetype === a)).map((a) => (
          <span key={a}><span className="dot" style={{ background: ARCHETYPE_COLOR[a] }} />{a}</span>
        ))}
        {overlay === 'risk' && <><span><span className="dot" style={{ background: '#0e9f6e' }} />low risk</span><span><span className="dot" style={{ background: '#d97706' }} />medium</span><span><span className="dot" style={{ background: '#dc2626' }} />high</span></>}
        {overlay === 'automation' && <span className="muted">Ring colour is the share of hours removed</span>}
        {overlay === 'priority' && <span className="muted">Ring weight is AI priority: hours removed over effort</span>}
        <span><span className="dot" style={{ background: 'var(--gate)', borderRadius: 2 }} />human gate</span>
        <span className="muted">dashed edge is a cross-group dependency</span>
      </div>

      {hoverEdge && (
        <div className="notice" style={{ marginTop: 10 }}>
          <strong>{hoverEdge.source} → {hoverEdge.target}</strong>{' '}
          carries {hoverEdge.payload} against {hoverEdge.schema_ref}.{' '}
          {hoverEdge.carries_pii ? 'Payload contains personal data and is masked in transit.' : 'No personal data in this payload.'}
          {hoverEdge.cross_tower && ' This edge crosses process groups, so the downstream agent cannot run unattended unless the upstream group is cleared.'}
        </div>
      )}
    </div>
  )
}
