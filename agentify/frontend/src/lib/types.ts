export type Band = 'full_agent' | 'hitl' | 'human_only'
export type Archetype = 'extraction' | 'reasoning' | 'generation' | 'monitoring' | 'orchestration'

export interface Evidence { kind: 'computed' | 'retrieved' | 'policy'; label: string; detail: string; source: string; score?: number | null }
export interface Override { rule: string; cap: number; reason: string; source: string }
export interface DimensionScore { key: string; label: string; weight: number; raw: number; weighted: number; basis: string }

export interface TaskRow {
  id: string; l1_code: string; l1_name: string; l2_code: string; l2_name: string
  l3_code: string; l3_name: string; l4_code: string; l4_name: string
  volume_per_month: number | null; avg_handle_minutes: number | null; fte: number | null
  rule_based: number | null; pii: boolean | null; systems: string | null; exception_rate: number | null
}

export interface ScoredTask {
  task: TaskRow; dimensions: DimensionScore[]; raw_score: number; score: number
  band: Band; confidence: number; resolution: string; overrides: Override[]
  evidence: Evidence[]; rationale: string; archetype: Archetype
  tokens: number; cost_usd: number
  human_override?: { from: string; to: string; reason: string; reviewer: string; at: string } | null
}

export interface AutomationEstimate {
  source_task_count: number; annual_hours_today: number; annual_hours_after: number
  hours_removed: number; fte_today: number; fte_after: number
  automation_pct: number; band_split: Record<string, number>
}

export interface AgentSpec {
  id: string; name: string; archetype: Archetype; purpose: string; model_tier: string
  tools: string[]; guardrails: string[]; io_contract: Record<string, string>
  source_task_ids: string[]; estimate: AutomationEstimate; risk_tier: string; generated_by: string
}

export interface AgentDependency { source: string; target: string; payload: string; schema_ref: string; carries_pii: boolean; cross_tower: boolean }
export interface HumanGate { id: string; before_agent: string; after_agents: string[]; reason: string; triggers: string[]; reviewer_role: string; task_count: number; est_review_minutes: number }
export interface TraceRow { task_id: string; l4_code: string; l4_name: string; l3_code: string; l1_code: string; agent_id: string; agent_name: string; band: Band; score: number; gate_id: string | null; resolution: string; evidence: Evidence[]; overrides: Override[] }

export interface CostReport {
  total_tokens: number; total_cost_usd: number; naive_cost_usd: number; saved_pct: number
  cost_per_1k_tasks: number; by_resolution: Record<string, number>
  by_stage: { stage: string; model: string; tier: string; tokens: number; cost_usd: number; calls: number; errors: number }[]
  cache_hit_rate: number; llm_calls: number; llm_calls_avoided: number
}

export interface BridgeStep { band: Band; label: string; fte_in_band: number; share_of_hours: number; residual: number; fte_removed: number; from: number; to: number }
export interface Bridge { fte_today: number; fte_after: number; steps: BridgeStep[]; residuals: Record<string, number> }

export interface Blueprint {
  run_id: string; industry: string; function: string; created_at: string; provider: string; mode: string
  task_count: number; agents: AgentSpec[]; dependencies: AgentDependency[]; gates: HumanGate[]
  traceability: TraceRow[]; scored_tasks: ScoredTask[]; cost: CostReport; bridge: Bridge
  band_totals: Record<string, number>; warnings: string[]
}

export interface StageEvent {
  run_id: string; stage_id: number; stage: string
  status: 'queued' | 'running' | 'done' | 'halted' | 'failed' | 'retrying'
  detail: string; progress: number; tokens: number; cost_usd: number
  model: string; elapsed_ms: number; payload_out: string; retries: number
}

export interface Industry { id: string; label: string; pattern: string; functions: string[]; sample: string; sample_available: boolean }
export interface InventoryResponse {
  inventory_id: string; filename: string
  summary: { l1: number; l2: number; l3: number; l4: number; with_effort: number; total_fte: number }
  warnings: string[]
  preview: { l1: string; l3: string; l4_code: string; l4_name: string; volume: number | null; fte: number }[]
}
