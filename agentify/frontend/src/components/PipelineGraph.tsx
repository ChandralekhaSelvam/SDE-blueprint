import type { StageEvent } from '../lib/types'

export const STAGES = [
  'Orchestrator',
  'Ingestion and parsing',
  'Feature extraction',
  'Classification and scoring',
  'Risk and compliance',
  'Architecture design',
  'Guardrail configuration',
  'Explainability',
  'Traceability and docs',
]

const W = 132
const H = 58
const GAP_X = 22
const GAP_Y = 68

/** Workers snake left to right on the top row, right to left on the bottom. */
function workerPos(index: number) {
  const perRow = 4
  const row = Math.floor(index / perRow)
  const inRow = index % perRow
  const col = row % 2 === 0 ? inRow : perRow - 1 - inRow
  return { x: 176 + col * (W + GAP_X), y: 8 + row * (H + GAP_Y) }
}

const STATUS_COLOR: Record<string, string> = {
  queued: 'var(--line-2)',
  running: '#2f6feb',
  done: '#0e9f6e',
  retrying: '#d97706',
  halted: '#d97706',
  failed: '#dc2626',
}

interface Props {
  events: StageEvent[]
  onSelectStage?: (stageId: number) => void
  selected?: number | null
}

export function PipelineGraph({ events, onSelectStage, selected }: Props) {
  // Last event per stage wins; the log is append-only so this is the live state.
  const latest = new Map<number, StageEvent>()
  events.forEach((e) => latest.set(e.stage_id, e))

  const workers = [1, 2, 3, 4, 5, 6, 7, 8]
  const positions = workers.map((_, i) => workerPos(i))
  const width = 176 + 4 * W + 3 * GAP_X + 8
  const height = 8 + 2 * H + GAP_Y + 8

  const orch = latest.get(0)
  const orchStatus = orch?.status ?? 'queued'

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="canvas" role="img"
           aria-label={`Pipeline: ${latest.size} of 9 stages reporting`}>
        <defs>
          <marker id="parrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6.5" markerHeight="6.5" orient="auto">
            <path d="M0,1 L7,4 L0,7" fill="none" stroke="var(--line-2)" strokeWidth="1.3" />
          </marker>
        </defs>

        {/* Control edges. Three is enough to read as supervision; eight is noise. */}
        {[0, 3, 7].map((i) => {
          const p = positions[i]
          return (
            <path key={`c${i}`} d={`M148,${height / 2} C${(148 + p.x) / 2},${height / 2} ${(148 + p.x) / 2},${p.y + H / 2} ${p.x},${p.y + H / 2}`}
                  className="edge" stroke="var(--orchestration)" strokeWidth="1" strokeDasharray="3 4" opacity="0.55" />
          )
        })}

        {/* Data handoffs along the snake. */}
        {positions.slice(0, -1).map((p, i) => {
          const n = positions[i + 1]
          const sameRow = p.y === n.y
          const from = latest.get(workers[i])
          const active = from?.status === 'done'
          const stroke = active ? 'var(--line-2)' : 'var(--line)'
          const d = sameRow
            ? (n.x > p.x ? `M${p.x + W},${p.y + H / 2} L${n.x - 4},${n.y + H / 2}` : `M${p.x},${p.y + H / 2} L${n.x + W + 4},${n.y + H / 2}`)
            : `M${p.x + W / 2},${p.y + H} L${n.x + W / 2},${n.y - 4}`
          return <path key={`d${i}`} d={d} className="edge" stroke={stroke} strokeWidth="1.4" markerEnd="url(#parrow)" />
        })}

        {/* Orchestrator. */}
        <g className="node" onClick={() => onSelectStage?.(0)}>
          <rect x={8} y={height / 2 - H / 2} width={140} height={H} rx={7}
                fill="var(--surface)" stroke={STATUS_COLOR[orchStatus]} strokeWidth={selected === 0 ? 2.6 : 2} />
          <text x={20} y={height / 2 - 8} className="node-label" fill="var(--ink)">Orchestrator</text>
          <text x={20} y={height / 2 + 8} className="node-meta" fill="var(--ink-3)">supervisor</text>
          <text x={20} y={height / 2 + 22} className="node-meta" fill="var(--ink-2)">{orchStatus}</text>
        </g>

        {workers.map((stageId, i) => {
          const p = positions[i]
          const e = latest.get(stageId)
          const status = e?.status ?? 'queued'
          const colour = STATUS_COLOR[status]
          const isSel = selected === stageId
          const label = STAGES[stageId]
          return (
            <g key={stageId} className="node" onClick={() => onSelectStage?.(stageId)} role="button" tabIndex={0}
               onKeyDown={(ev) => { if (ev.key === 'Enter') onSelectStage?.(stageId) }}
               aria-label={`${label}: ${status}`}>
              <rect x={p.x} y={p.y} width={W} height={H} rx={7} fill="var(--surface)"
                    stroke={colour} strokeWidth={isSel ? 2.6 : status === 'queued' ? 1.3 : 2} />
              <text x={p.x + 10} y={p.y + 20} className="node-label"
                    fill={status === 'queued' ? 'var(--ink-3)' : 'var(--ink)'}>
                {stageId} {label.length > 18 ? `${label.slice(0, 17)}…` : label}
              </text>
              <text x={p.x + 10} y={p.y + 36} className="node-meta" fill="var(--ink-3)">
                {e?.model && e.model !== 'none' ? e.model.slice(0, 16) : status === 'queued' ? 'queued' : 'no model'}
              </text>
              <text x={p.x + 10} y={p.y + 50} className="node-meta" fill={colour}>
                {status === 'running' && e?.progress ? `${Math.round(e.progress * 100)}%` : status}
              </text>
              {status === 'running' && (
                <rect x={p.x} y={p.y + H - 3} width={W * (e?.progress || 0.06)} height={3} fill={colour} rx={1.5} />
              )}
            </g>
          )
        })}
      </svg>

      <div className="legend">
        <span><span className="dot" style={{ background: '#0e9f6e' }} />done</span>
        <span><span className="dot" style={{ background: '#2f6feb' }} />running</span>
        <span><span className="dot" style={{ background: 'var(--line-2)' }} />queued</span>
        <span className="muted">dashed edge is orchestrator control, solid is a data handoff</span>
      </div>
    </div>
  )
}

export function StageLog({ events }: { events: StageEvent[] }) {
  const done = events.filter((e) => e.status !== 'running' || e.progress === 0)
  return (
    <div>
      {done.slice(-14).reverse().map((e, i) => (
        <div className="stage-row" key={i}>
          <span className={`stage-dot ${e.status}`} />
          <span style={{ minWidth: 168 }}>{e.stage}</span>
          <span className="dim" style={{ flex: 1 }}>{e.detail}</span>
          {e.elapsed_ms > 0 && <span className="mono muted" style={{ fontSize: 11 }}>{e.elapsed_ms} ms</span>}
        </div>
      ))}
    </div>
  )
}
