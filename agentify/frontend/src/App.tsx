import { useCallback, useEffect, useState } from 'react'
import { api } from './lib/api'
import { Intake } from './components/Intake'
import { MeshGraph } from './components/MeshGraph'
import { PipelineGraph, StageLog } from './components/PipelineGraph'
import { AgentDrawer, Catalog, Cost, Gates, TaskDrawer, Traceability } from './components/Panels'
import type { Blueprint, InventoryResponse, StageEvent } from './lib/types'

type Screen = 'intake' | 'running' | 'workspace'
type Tab = 'catalog' | 'dependencies' | 'gates' | 'traceability' | 'cost'
type Overlay = 'archetype' | 'automation' | 'risk' | 'priority'

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'catalog', label: 'Catalog', hint: 'structured agent catalog' },
  { id: 'dependencies', label: 'Dependencies', hint: 'agent dependencies' },
  { id: 'gates', label: 'Human gates', hint: 'human-in-the-loop points' },
  { id: 'traceability', label: 'Traceability', hint: 'traceable to source task' },
  { id: 'cost', label: 'Cost', hint: 'automation estimate and spend' },
]

export default function App() {
  const [screen, setScreen] = useState<Screen>('intake')
  const [tab, setTab] = useState<Tab>('catalog')
  const [view, setView] = useState<'mesh' | 'pipeline'>('mesh')
  const [overlay, setOverlay] = useState<Overlay>('archetype')
  const [simulate, setSimulate] = useState(false)

  const [config, setConfig] = useState<any>(null)
  const [events, setEvents] = useState<StageEvent[]>([])
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [agentId, setAgentId] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)

  useEffect(() => { api.health().then((h) => setConfig(h.config)).catch(() => {}) }, [])

  const start = useCallback(async (inv: InventoryResponse, industry: string, fn: string) => {
    setError(null)
    setEvents([])
    setBlueprint(null)
    setScreen('running')
    try {
      const { run_id } = await api.createRun(inv.inventory_id, industry, fn)
      api.stream(run_id, {
        stage: (e) => setEvents((prev) => [...prev, e]),
        blueprint: (b) => { setBlueprint(b); setScreen('workspace') },
        error: (m) => { setError(m); setScreen('intake') },
        end: () => {},
      })
    } catch (e: any) {
      setError(e.message)
      setScreen('intake')
    }
  }, [])

  const override = useCallback(async (tid: string, band: string, reason: string) => {
    if (!blueprint) return
    await api.override(blueprint.run_id, tid, band, reason, 'demo reviewer')
    setBlueprint({
      ...blueprint,
      scored_tasks: blueprint.scored_tasks.map((t) => t.task.id === tid ? { ...t, band: band as any } : t),
      traceability: blueprint.traceability.map((r) => r.task_id === tid ? { ...r, band: band as any } : r),
    })
  }, [blueprint])

  const agent = blueprint?.agents.find((a) => a.id === agentId) ?? null
  const task = blueprint?.scored_tasks.find((t) => t.task.id === taskId) ?? null

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Agentification blueprint</span>
        {config && (
          <span className={`pill ${config.live ? 'live' : 'demo'}`}>
            {config.live ? `live · ${config.provider}` : 'demo · no model calls'}
          </span>
        )}
        {blueprint && (
          <span className="muted mono" style={{ fontSize: 12 }}>
            {blueprint.industry.replace('_', ' ')} · {blueprint.function} · {blueprint.task_count} activities
          </span>
        )}
        <span className="spacer" />
        {blueprint && <button className="btn small" onClick={() => { setScreen('intake'); setBlueprint(null) }}>New blueprint</button>}
      </header>

      {screen === 'workspace' && blueprint && (
        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.id} className="tab" role="tab" aria-selected={tab === t.id}
                    title={t.hint} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </nav>
      )}

      <main className="main">
        {error && (
          <div className="error" style={{ marginBottom: 16 }}>
            <strong>The run could not finish.</strong>
            <div>{error}</div>
          </div>
        )}

        {screen === 'intake' && <Intake onReady={start} />}

        {screen === 'running' && (
          <div className="stack" style={{ maxWidth: 1000, margin: '0 auto' }}>
            <div className="card card-pad">
              <h2>Building the blueprint</h2>
              <p className="dim" style={{ fontSize: 13 }}>
                One supervisor and eight workers. Each stage owns a single contract and hands a
                named payload to the next.
              </p>
              <PipelineGraph events={events} />
            </div>
            <div className="card card-pad">
              <h3>Run log</h3>
              <StageLog events={events} />
            </div>
          </div>
        )}

        {screen === 'workspace' && blueprint && (
          <>
            {blueprint.warnings.map((w, i) => (
              <div className="notice" key={i} style={{ marginBottom: 12 }}>{w}</div>
            ))}

            {tab === 'catalog' && <Catalog bp={blueprint} onSelect={setAgentId} />}

            {tab === 'dependencies' && (
              <div className="card">
                <div className="card-head">
                  <button className="chip" aria-pressed={view === 'mesh'} onClick={() => setView('mesh')}>Generated mesh</button>
                  <button className="chip" aria-pressed={view === 'pipeline'} onClick={() => setView('pipeline')}>Pipeline run</button>
                  <span className="spacer" />
                  {view === 'mesh' && (
                    <>
                      {(['archetype', 'automation', 'risk', 'priority'] as Overlay[]).map((o) => (
                        <button key={o} className="chip" aria-pressed={overlay === o} onClick={() => setOverlay(o)}>{o}</button>
                      ))}
                      <button className="btn small" onClick={() => setSimulate((s) => !s)}>
                        {simulate ? 'Stop' : 'Send a work item'}
                      </button>
                    </>
                  )}
                </div>
                <div className="card-pad">
                  {view === 'mesh' ? (
                    <MeshGraph agents={blueprint.agents} dependencies={blueprint.dependencies}
                               gates={blueprint.gates} selected={agentId} onSelect={setAgentId}
                               overlay={overlay} simulating={simulate} />
                  ) : (
                    <>
                      <PipelineGraph events={events} />
                      <div style={{ marginTop: 14 }}><StageLog events={events} /></div>
                    </>
                  )}
                </div>
              </div>
            )}

            {tab === 'gates' && <Gates bp={blueprint} />}
            {tab === 'traceability' && <Traceability bp={blueprint} onSelectTask={setTaskId} />}
            {tab === 'cost' && <Cost bp={blueprint} />}
          </>
        )}
      </main>

      {agent && blueprint && <AgentDrawer bp={blueprint} agent={agent} onClose={() => setAgentId(null)} />}
      {task && blueprint && <TaskDrawer bp={blueprint} task={task} onClose={() => setTaskId(null)} onOverride={override} />}
    </div>
  )
}
