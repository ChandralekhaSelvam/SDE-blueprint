import type { Blueprint, Industry, InventoryResponse, StageEvent } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed with ${res.status}.`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep the status message */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => fetch(`${BASE}/api/health`).then(unwrap<{ ok: boolean; config: any }>),

  industries: () => fetch(`${BASE}/api/industries`).then(unwrap<{ industries: Industry[] }>),

  /** Upload a process inventory. The file is parsed and validated immediately. */
  upload(file: File) {
    const form = new FormData()
    form.append('file', file, file.name)
    return fetch(`${BASE}/api/inventory`, { method: 'POST', body: form }).then(unwrap<InventoryResponse>)
  },

  sample(industry: string) {
    const form = new FormData()
    form.append('industry', industry)
    return fetch(`${BASE}/api/inventory/sample`, { method: 'POST', body: form }).then(unwrap<InventoryResponse>)
  },

  createRun(inventory_id: string, industry: string, fn: string) {
    return fetch(`${BASE}/api/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inventory_id, industry, function: fn }),
    }).then(unwrap<{ run_id: string }>)
  },

  /**
   * Stream a run. Uses EventSource, so the pipeline graph updates per stage
   * rather than after the whole run. Returns a cancel function.
   */
  stream(
    runId: string,
    handlers: { stage: (e: StageEvent) => void; blueprint: (b: Blueprint) => void; error: (m: string) => void; end: () => void },
  ) {
    const source = new EventSource(`${BASE}/api/runs/${runId}/stream`)
    source.addEventListener('stage', (e) => handlers.stage(JSON.parse((e as MessageEvent).data)))
    source.addEventListener('blueprint', (e) => handlers.blueprint(JSON.parse((e as MessageEvent).data)))
    source.addEventListener('error', (e) => {
      const data = (e as MessageEvent).data
      if (data) handlers.error(JSON.parse(data).message)
    })
    source.addEventListener('end', () => { source.close(); handlers.end() })
    source.onerror = () => { source.close(); handlers.error('Lost the connection to the run stream.') }
    return () => source.close()
  },

  override(runId: string, task_id: string, new_band: string, reason: string, reviewer: string) {
    return fetch(`${BASE}/api/runs/${runId}/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id, new_band, reason, reviewer }),
    }).then(unwrap<{ ok: boolean }>)
  },

  traceabilityUrl: (runId: string) => `${BASE}/api/runs/${runId}/export/traceability.csv`,
  blueprintUrl: (runId: string) => `${BASE}/api/runs/${runId}/export/blueprint.json`,
}
