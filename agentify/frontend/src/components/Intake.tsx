import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { Industry, InventoryResponse } from '../lib/types'

const SWATCH: Record<string, string> = {
  industrial: '#2f6feb',
  consumer_products: '#0e9f6e',
  life_sciences: '#7a5af8',
  telecom: '#d97706',
}

interface Props {
  onReady: (inv: InventoryResponse, industry: string, fn: string) => void
}

export function Intake({ onReady }: Props) {
  const [industries, setIndustries] = useState<Industry[]>([])
  const [industry, setIndustry] = useState('consumer_products')
  const [fn, setFn] = useState('Legal')
  const [inventory, setInventory] = useState<InventoryResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.industries()
      .then((d) => setIndustries(d.industries))
      .catch((e) => setError(`Could not reach the backend. ${e.message}`))
  }, [])

  const current = industries.find((i) => i.id === industry)

  useEffect(() => {
    if (current && !current.functions.includes(fn)) setFn(current.functions[0])
  }, [industry, current])

  async function take(promise: Promise<InventoryResponse>) {
    setBusy(true)
    setError(null)
    try {
      setInventory(await promise)
    } catch (e: any) {
      setError(e.message)
      setInventory(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 900, margin: '0 auto' }}>
      <div>
        <h1>Scope a tower for agents</h1>
        <p className="dim">
          Give it an L1 to L4 process list and it returns an agent catalog with dependencies,
          the points where a human stays in the loop, and an automation estimate for every agent,
          each one traceable back to the activity it came from.
        </p>
      </div>

      <div className="card card-pad">
        <h3>Industry</h3>
        <div className="grid-4">
          {industries.map((item) => (
            <button key={item.id} className="industry" aria-pressed={industry === item.id}
                    onClick={() => setIndustry(item.id)}>
              <div className="swatch" style={{ background: SWATCH[item.id] ?? 'var(--ink-3)' }} />
              <div className="name">{item.label}</div>
              <div className="muted" style={{ fontSize: 12 }}>{item.pattern}</div>
            </button>
          ))}
          {!industries.length && <p className="muted">Loading industries…</p>}
        </div>

        <h3 style={{ marginTop: 18 }}>Business function</h3>
        <div className="chips">
          {(current?.functions ?? []).map((f) => (
            <button key={f} className="chip" aria-pressed={fn === f} onClick={() => setFn(f)}>{f}</button>
          ))}
        </div>
      </div>

      <div className="card card-pad">
        <h3>Process inventory</h3>
        <div
          className={`drop ${over ? 'over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setOver(false)
            const file = e.dataTransfer.files?.[0]
            if (file) take(api.upload(file))
          }}
        >
          <p style={{ margin: '0 0 4px', fontWeight: 500 }}>Drop an L1 to L4 process list here</p>
          <p className="muted" style={{ fontSize: 12.5, margin: '0 0 12px' }}>
            CSV, XLSX or JSON. Column names are matched loosely, so an export straight from the
            client's own inventory usually works without editing.
          </p>
          <div className="row" style={{ justifyContent: 'center' }}>
            <button className="btn" onClick={() => fileRef.current?.click()} disabled={busy}>Choose a file</button>
            {current?.sample_available && (
              <button className="btn" disabled={busy} onClick={() => take(api.sample(industry))}>
                Use the {current.label.toLowerCase()} sample
              </button>
            )}
          </div>
          <input ref={fileRef} type="file" hidden accept=".csv,.tsv,.txt,.xlsx,.xlsm,.xls,.json"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) take(api.upload(f)); e.target.value = '' }} />
        </div>

        {busy && <p className="muted" style={{ marginTop: 12 }}>Reading the file…</p>}

        {error && (
          <div className="error" style={{ marginTop: 12 }}>
            <strong>That file could not be read.</strong>
            <div style={{ marginTop: 4 }}>{error}</div>
          </div>
        )}

        {inventory && (
          <div style={{ marginTop: 16 }}>
            <div className="row" style={{ marginBottom: 12 }}>
              <strong>{inventory.filename}</strong>
              <span className="pill">parsed</span>
            </div>
            <div className="stats">
              <div className="stat"><div className="v">{inventory.summary.l1}</div><div className="k">L1</div></div>
              <div className="stat"><div className="v">{inventory.summary.l2}</div><div className="k">L2</div></div>
              <div className="stat"><div className="v">{inventory.summary.l3}</div><div className="k">L3</div></div>
              <div className="stat"><div className="v">{inventory.summary.l4}</div><div className="k">L4 activities</div></div>
              <div className="stat"><div className="v">{inventory.summary.total_fte}</div><div className="k">FTE in scope</div></div>
            </div>

            {inventory.warnings.map((w, i) => (
              <div className="notice" key={i} style={{ marginTop: 10 }}>{w}</div>
            ))}

            <div className="scroll" style={{ marginTop: 14, maxHeight: 200 }}>
              <table>
                <thead>
                  <tr><th>L4</th><th>Activity</th><th className="num">Volume</th><th className="num">FTE</th></tr>
                </thead>
                <tbody>
                  {inventory.preview.map((r) => (
                    <tr key={r.l4_code}>
                      <td className="mono muted">{r.l4_code}</td>
                      <td>{r.l4_name}</td>
                      <td className="num">{r.volume?.toLocaleString() ?? '—'}</td>
                      <td className="num">{r.fte || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="row" style={{ marginTop: 16 }}>
              <button className="btn primary" onClick={() => onReady(inventory, industry, fn)}>
                Generate the blueprint
              </button>
              <span className="muted" style={{ fontSize: 12.5 }}>
                {inventory.summary.l4} activities, {current?.label.toLowerCase()} policy pack, {fn.toLowerCase()} tower
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
