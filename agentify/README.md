# Agentification Blueprint Assistant

Feed it an L1–L4 process list. Get back an agent catalog with dependencies, the
points where a human stays in the loop, and an automation estimate for every
agent — each one traceable to the activity it came from.

Built for **PS 02 — Agentification Scoping & Blueprint Assistant for GBS Towers**.

---

## Contents

- [What it does](#what-it-does)
- [Definition of done](#definition-of-done)
- [Quick start](#quick-start)
- [Run modes](#run-modes)
- [Model providers](#model-providers)
- [Architecture](#architecture)
- [The scoring engine](#the-scoring-engine)
- [How tokens are saved](#how-tokens-are-saved)
- [Responsible AI](#responsible-ai)
- [The effort bridge](#the-effort-bridge)
- [Upload contract](#upload-contract)
- [API reference](#api-reference)
- [Frontend](#frontend)
- [Deploying to GCP](#deploying-to-gcp)
- [Testing](#testing)
- [Extending it](#extending-it)
- [Known limits](#known-limits)

---

## What it does

Scoping a GBS tower for agents is done by hand today: an architect reads a
process inventory, forms a view on what could be automated, and writes it up.
The exercise is slow, inconsistent between people, and hard to defend when a
client asks why a particular activity was classified the way it was.

This turns that into a repeatable pipeline.

```
process inventory  →  seven weighted dimensions  →  policy overrides
                   →  agent catalog + dependencies + gates + estimate
                   →  traceability matrix + cost report
```

Every classification carries its arithmetic, its evidence, and the policy rule
that capped it, if one did. Nothing in the output is unattributable.

## Definition of done

The problem statement is specific. Each clause maps to a tab in the UI, an
object in `schemas.py`, and a test in `tests/test_blueprint.py`.

| DoD clause | Object | UI tab | Test |
|---|---|---|---|
| structured agent catalog | `AgentSpec` | Catalog | `test_dod_agent_catalog` |
| with dependencies | `AgentDependency` | Dependencies | `test_dod_dependencies` |
| human-in-the-loop points | `HumanGate` | Human gates | `test_dod_human_gates` |
| per-agent automation estimate | `AutomationEstimate` | Catalog, Cost | `test_dod_automation_estimate_per_agent` |
| each traceable to its source task | `TraceRow` | Traceability | `test_dod_every_row_traces_to_its_source_task` |

`make test` asserts all five on a real run.

---

## Quick start

Nothing to configure. Demo mode makes no network calls.

```bash
git clone <repo> && cd agentify
make install
make demo
```

Open `http://localhost:5173`, pick an industry, click **Use the … sample**, and
generate. The whole flow runs offline.

With Docker:

```bash
docker compose up --build      # frontend on :5173, backend on :8000
```

---

## Run modes

Set by `RUN_MODE` in `.env`.

### `demo` — no network calls at all

The deterministic scorer produces a complete blueprint on its own. Every DoD
artifact is populated, every band is represented, the cost report is real. The
mock provider returns well-formed JSON shaped exactly like a real adjudication,
seeded from the prompt hash, so the same input always yields the same output.

Use it for offline demos, CI, and any situation where you cannot risk a network
hiccup in front of an audience.

### `live` — the same pipeline, plus adjudication

Identical flow. A model is consulted only where the deterministic result is
genuinely uncertain, which is a narrow window by design:

- the score sits inside `AMBIGUOUS_LOW`–`AMBIGUOUS_HIGH` (default 55–80), **or**
- confidence is below `CONFIDENCE_FLOOR` (default 0.85)

A task whose score was capped by policy is **never** adjudicated. Policy already
decided it, and spending a model call to second-guess a deterministic rule is
waste.

### Degradation is a first-class path

Bad key, rate limit, timeout, budget exhausted, call ceiling hit — all resolve
to "keep the deterministic answer and add a warning". The run always completes.

```
$ RUN_MODE=live LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-invalid python -m pytest -k provider_failure
RUN COMPLETED: True
agents 5 | gates 2 | trace 17
warn - anthropic unavailable: HTTP 401 … Falling back to deterministic scoring.
```

This is the single most important property of the design. The app runs on a
low-tier model, on a broken model, or on no model.

---

## Model providers

Set by `LLM_PROVIDER`. Every provider implements one method and returns the
same `LLMResult`, so nothing downstream branches on vendor.

| Provider | Value | Auth | Notes |
|---|---|---|---|
| Mock | `mock` | none | Offline, seeded, free |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | Prompt caching on the static system block |
| Google Vertex AI | `vertex` | ADC or service account | REST `generateContent`, only needs `google-auth` |
|  Generative Engine | `genengine` | `GENENGINE_BASE_URL` + `GENENGINE_API_KEY` | OpenAI-compatible `/chat/completions` |

Each exposes three tiers. Map them to whatever your account is entitled to:

```bash
# Anthropic
ANTHROPIC_MODEL_SMALL=claude-haiku-4-5-20251001
ANTHROPIC_MODEL_MEDIUM=claude-sonnet-5
ANTHROPIC_MODEL_LARGE=claude-opus-5

# Vertex
VERTEX_MODEL_SMALL=gemini-2.5-flash-lite
VERTEX_MODEL_MEDIUM=gemini-2.5-flash
VERTEX_MODEL_LARGE=gemini-2.5-pro

# Generative Engine — whatever your tenant exposes
GENENGINE_MODEL_SMALL=gpt-4o-mini
GENENGINE_MODEL_MEDIUM=gpt-4o
GENENGINE_MODEL_LARGE=claude-sonnet-4
```

**Running well on a cheap model is a design goal, not a fallback.** The router
sends feature work to `small`, ambiguous adjudication to `small` or `medium`
depending on confidence, and `large` only for agent description — once per
agent, not once per task. Point all three tiers at the same small model and the
blueprint is still correct; only the prose in agent purposes gets plainer.

### Budget ceilings

```bash
MAX_LLM_CALLS=60      # hard cap on calls per run
BUDGET_USD=2.00       # hard cap on spend per run
```

The router checks both before every call and degrades rather than overspends.
A runaway inventory cannot produce a runaway bill.

---

## Architecture

```
frontend/                React 18 + Vite + TypeScript, no UI framework
  src/components/
    Intake.tsx           industry, function, upload
    MeshGraph.tsx        generated agent mesh, layered DAG
    PipelineGraph.tsx    the nine agents building the blueprint, live
    Panels.tsx           catalog, gates, traceability, cost, bridge, drawers
  src/lib/
    api.ts               fetch + EventSource client
    types.ts             mirrors backend schemas

backend/
  app/
    main.py              FastAPI: upload, runs, SSE, override, export, audit
    schemas.py           the DoD contract
    config.py            run mode, provider, tiers, budgets
    ingest.py            tolerant CSV/XLSX/JSON parsing
    scoring.py           seven weighted dimensions — no model calls, ever
    policy.py            hard overrides, per-industry packs
    pii.py               redaction at ingest and on handoffs
    cache.py             task-level result cache, sqlite
    llm/                 base, mock, anthropic, vertex, genengine, router
    agents/
      pipeline.py        the nine-agent orchestration
      architect.py       catalog, dependencies, gates, estimates
  policy/                per-industry YAML overrides
  tests/

mock-data/               four sample inventories
```

### The nine agents

One supervisor and eight workers, each owning a single stage with its own
contract. Stages emit `StageEvent`s that the API forwards over SSE and the
frontend renders as the live pipeline graph.

| # | Agent | Model | Does |
|---|---|---|---|
| 0 | Orchestrator | none | Sequences stages, retries, halts at gates |
| 1 | Ingestion and parsing | none | Schema validation, L1–L4 normalisation, PII masking |
| 2 | Feature extraction | small | Derives scoring features from the inventory |
| 3 | Classification and scoring | small/medium | Seven dimensions, adjudication where uncertain |
| 4 | Risk and compliance | none | Independent review, can veto or downgrade |
| 5 | Architecture design | large | Groups activities into agents, generates specs |
| 6 | Guardrail configuration | none | Sizes guardrails to each agent's risk tier |
| 7 | Explainability | none | Criteria-level rationale and evidence records |
| 8 | Traceability and docs | none | The L1→L4→agent matrix |

Six of nine stages make no model call at all.

The pipeline is an explicit stage list rather than a graph library, so the whole
run is inspectable and there is no orchestration dependency to install. Swapping
in LangGraph means implementing `Pipeline.run` as a `StateGraph` over the same
stage functions — the events and contracts do not change.

---

## The scoring engine

Seven weighted dimensions, summing to 1.00. Pure arithmetic in `scoring.py`.

| Dimension | Weight | Derived from | Fallback when absent |
|---|---|---|---|
| Task frequency | 0.15 | Monthly volume, log-scaled | Median |
| Rule-based nature | 0.20 | Supplied score, or the activity verb | Keyword inference |
| Data sensitivity | 0.15 | PII flag | Sensitivity keywords |
| Decision complexity | 0.20 | Exception rate | Judgement-word count |
| Integration maturity | 0.10 | System count, API signals | Assumed partial |
| ROI potential | 0.10 | Annual hours, log-scaled | Assumed low |
| Data availability | 0.10 | How complete the source row is | Computed always |

Frequency is log-scaled deliberately: an activity run 20,000 times a month is
not twenty times more automatable than one run 1,000 times, but it is
meaningfully more so.

### Bands

| Band | Score | Meaning |
|---|---|---|
| Full agent | ≥ 75 | Executes autonomously with full audit logging |
| Human in the loop | 40–74 | AI proposes, a human approves or edits |
| Human only | < 40 | AI supports with context; a human decides |

### Hard overrides

Deterministic caps from version-controlled YAML. **No model decides a risk tier.**

| Rule | Cap | Fires when |
|---|---|---|
| `pii` | 60 | The activity handles personal data |
| `safety_critical` | 45 | Safety-critical outcome |
| `executive_judgement` | 30 | Executive or strategic judgement |
| `judgement_dominant` | 35 | Neither rule-bound nor low-complexity |

Plus per-industry rules: `contract_commitment` (consumer products), `gxp`
(life sciences), `supplier_payment` (industrial), `cpni` (telecom).

`judgement_dominant` is the one worth understanding. Without it, a high-volume
judgement activity — "negotiate a settlement", run 9,000 times a month — gets
pulled into the automatable band by frequency and ROI alone. Volume must never
make judgement work automatable, so the rule is computed rather than
keyword-matched.

Keyword rules match **the activity name and its notes only**, never the process
group above it. Matching the whole L1–L4 path would fire a contract rule on
every activity in a group merely called "Contract Management" — a bug this code
had, and which `test_keyword_rules_do_not_match_the_process_group_name` now
prevents from returning.

### Confidence

```
confidence = 0.55 + completeness × 0.45 − boundary_penalty
```

Falls when the source row is thin, and when the score sits near a band edge.
Below `CONFIDENCE_FLOOR` the task is either adjudicated or routed to a gate.

---

## How tokens are saved

Measured on a real run in the Cost tab, not estimated.

**1. Deterministic first.** The composite is arithmetic over features. On the
sample inventories roughly 85% of activities never reach a model.

**2. Narrow adjudication window.** Only scores in 55–80, or confidence under
0.85, are eligible. A capped task is excluded entirely.

**3. Task-level cache.** APQC activities repeat heavily across towers and
clients — "extract key clauses from NDA" is near-identical whether the account
is Unilever or CSL. The cache keys on a normalised token bag with Jaccard
similarity rather than embeddings, deliberately: no embedding call means the
lookup is itself free, which matters when the point is to avoid spend. Swap in
pgvector for production without changing the interface.

**4. Prompt caching.** The rubric and policy pack are identical on every call in
a run. On Anthropic they go in the system block behind a `cache_control`
breakpoint. Paying for that context once instead of 300 times is the largest
single prompt saving available.

**5. Model tiering.** Small for features, small or medium for adjudication,
large once per agent for description. Never large per task.

**6. Constrained output.** JSON only, prefilled opening brace on Anthropic,
`response_format` on the OpenAI-compatible surface, tight `max_tokens`.

**7. Hard ceilings.** Budget and call caps degrade to deterministic rather than
overspending.

The Cost tab shows a disposition bar — deterministic, cache, small model, large
model — a routing ledger by stage and model, and the run cost beside a naive
baseline of one medium-tier call per activity.

---

## Responsible AI

**The system scores activities, never people.** It is stated in the UI beneath
the effort bridge. A tool that recommends a headcount shift has to be
unambiguous that it classifies work, and that redeployment decisions belong to
humans with names.

**Guardrails are not model judgement.** Every cap traces to a named rule in a
named file at a named line, shown in the evidence panel. When someone asks "what
if the model is wrong about risk", the answer is that the model was never
consulted.

**Separation of duties.** Stage 4 reviews high-impact classifications
independently and can veto an autonomous classification regardless of what the
scorer or a model concluded. That maps onto a second-line-of-defence control
every GBS compliance officer recognises.

**PII masked at the boundary.** Client SOPs routinely carry employee names, case
references and account numbers in free-text columns. `pii.py` runs at ingest and
on every agent handoff. Nothing reaches a model provider or the cache unmasked.
Deterministic regex rather than an ML recogniser, because it runs on every row
of every upload and an auditable redactor beats a probabilistic one here.

**Every classification carries evidence.** Three provenance kinds, and the
distinction is the point:

- `computed` — arithmetic, no model involved
- `retrieved` — a model or cache result, with its source and similarity
- `policy` — a rule from a YAML file, with its path

**Human override is first class.** A reason is mandatory; the API rejects a
blank one. Changes are attributed, timestamped and written to the audit log at
`GET /api/audit`.

**Honest uncertainty.** Rows without volume data are reported as producing a
range rather than a point. Residual factors are labelled as assumptions.
Warnings surface in the workspace, not buried in a log.

---

## The effort bridge

The arithmetic that makes a large headcount shift defensible, and the part most
often got wrong.

Task counts and hour counts diverge sharply. A run can be 31% full-agent by task
and still remove most of the effort, because a small set of high-volume
activities carries the majority of the hours. So everything is weighted by
`volume × handle time`, never by row count.

Three mechanisms, not one:

| Mechanism | Residual | Reasoning |
|---|---|---|
| Autonomous execution | 4% | Exception handling remains |
| Reviewed, not drafted | 15% | Approving a draft is faster than producing one |
| AI-assisted human work | 80% | Judgement work still gets a modest lift |

The middle row carries the case. Human-in-the-loop work is usually modelled as
zero saving; in practice a reviewed activity drops from roughly 30 minutes of
drafting to 4 minutes of approving. On the Unilever Legal sample the bridge
gives **62.7 → 17.1 FTE**.

Residuals are configurable per industry in `policy/<industry>.yaml`. Make them
editable in front of a client — someone who can drag the HITL residual and watch
the target move will trust the model, because they have tested it.

---

## Upload contract

The upload path is deliberately two-phase, because a file that fails halfway
through a demo is worse than one that fails at the door.

```
POST /api/inventory   → parse, validate, return a summary and an inventory_id
POST /api/runs        → commit to a run against that inventory_id
```

Nothing is scored until the user has seen what was actually read.

**Only `L4 Name` is required.** Everything else improves confidence and is
reported as missing when absent.

The parser handles, without configuration:

- CSV, TSV, XLSX, XLSM, XLS, JSON
- Comma, semicolon, tab or pipe delimiters, detected from content
- Title blocks above the real header (scans the first twelve rows)
- Multi-sheet workbooks, picking the sheet that looks like a process list
- Column aliases: `PCF ID`, `Activity Name`, `AHT`, `Rule Bound %`, `Contains PII`, and about forty more
- Excel turning `9.0` into `9`
- Booleans as `Y/N`, `Yes/No`, `true/false`, `1/0`
- Percentages as `0.08` or `8%`
- Short rows, blank rows, `utf-8-sig` BOMs

Failure modes return a precise 4xx with a message written for the user, never a
stack trace:

```
415  Unsupported file type. Upload one of: .csv, .tsv, .txt, .xlsx, .xlsm, .xls, .json.
413  File is 24.1 MB. The limit is 20 MB.
400  The uploaded file is empty.
422  junk.csv parsed but contained no rows.
422  No activity name column found. Expected a column like 'L4 Name', 'Activity', or 'Task name'.
```

`mock-data/charter-care.csv` exists specifically to exercise this: two title
rows above the header and entirely non-standard column names.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Config, cache stats, run count |
| `GET` | `/api/industries` | Industry cards and sample availability |
| `POST` | `/api/inventory` | Upload and parse a process list |
| `POST` | `/api/inventory/sample` | Load a bundled sample |
| `POST` | `/api/runs` | Create a run |
| `GET` | `/api/runs/{id}/stream` | SSE: `stage`, `blueprint`, `error`, `end` |
| `POST` | `/api/runs/{id}/execute` | Synchronous run, for scripts and tests |
| `GET` | `/api/runs/{id}` | Run status, events and blueprint |
| `POST` | `/api/runs/{id}/override` | Change a band; reason required |
| `GET` | `/api/audit` | Audit log |
| `GET` | `/api/runs/{id}/export/traceability.csv` | Traceability matrix |
| `GET` | `/api/runs/{id}/export/blueprint.json` | Full blueprint |

Interactive docs at `http://localhost:8000/docs`.

```bash
# End to end from the shell
ID=$(curl -s -F "file=@mock-data/unilever-legal.csv" localhost:8000/api/inventory | jq -r .inventory_id)
RUN=$(curl -s -X POST localhost:8000/api/runs -H 'Content-Type: application/json' \
  -d "{\"inventory_id\":\"$ID\",\"industry\":\"consumer_products\",\"function\":\"Legal\"}" | jq -r .run_id)
curl -s -X POST localhost:8000/api/runs/$RUN/execute | jq '.band_totals, .bridge.fte_after'
```

---

## Frontend

React 18 + Vite + TypeScript. No component library, no CSS framework — plain CSS
with custom properties, which keeps the bundle at 56 kB gzipped and means the
graph rendering is fully under our control.

**Design.** Cool technical paper. One sans family; the mono face is reserved for
process codes, scores and token counts, where column alignment genuinely helps
scanning. Colour is never decorative: hue carries agent archetype, weight
carries run state. Dark mode via `prefers-color-scheme`.

**Two graph canvases, one visual grammar.**

The *generated mesh* is the client's future agents. Layout is Sugiyama-lite:
column comes from archetype order, so the graph always reads left to right as
extract, reason, generate, monitor. Stable across runs, which matters — a client
comparing two towers should see the same shape move, not a different random
layout. Four overlays mirror the APQC master map's own view switcher: archetype,
automation, risk, AI priority.

The *pipeline run* is the nine agents that built the blueprint, streaming live.
Solid edges are data handoffs, dashed edges are orchestrator control. Both live
behind a segmented control on the Dependencies tab.

**Interaction.** Nodes and edges are both clickable. An edge is a data contract —
what payload passes, its schema, whether it carries PII, whether it crosses
process groups. The cross-group edge surfaces the honest finding: an agent that
scores well in isolation but cannot run unattended because something upstream is
human-only.

**Motion.** Nodes fade in as the architecture emits them, once. Edge flow is
opt-in behind a **Send a work item** button rather than looping ambiently.
`prefers-reduced-motion` disables both.

**Accessibility.** Keyboard-navigable graph nodes, visible focus rings, ARIA
labels on both canvases, no colour-only encoding.

---

## Deploying to GCP

### Cloud Run

```bash
PROJECT=your-project
REGION=us-central1

# Backend
gcloud run deploy blueprint-api \
  --source . --dockerfile backend/Dockerfile \
  --region $REGION --allow-unauthenticated \
  --set-env-vars "RUN_MODE=live,LLM_PROVIDER=vertex,GCP_PROJECT=$PROJECT,GCP_LOCATION=$REGION" \
  --service-account blueprint-sa@$PROJECT.iam.gserviceaccount.com \
  --timeout 900 --memory 1Gi

# Frontend
cd frontend && npm run build
gcloud run deploy blueprint-ui --source . --region $REGION --allow-unauthenticated
```

The service account needs `roles/aiplatform.user`. No key material: `google-auth`
picks up the attached identity through ADC. Locally, `gcloud auth
application-default login` is enough.

Two Cloud Run notes. Set `--timeout 900` or long SSE streams get cut. Set
`--min-instances 1` before a demo so nobody watches a cold start.

###  Generative Engine

```bash
RUN_MODE=live
LLM_PROVIDER=genengine
GENENGINE_BASE_URL=https://<your-tenant>/v1
GENENGINE_API_KEY=<key>
```

Same pipeline, same output shape. Only `llm/genengine_provider.py` changes.

---

## Testing

```bash
make test        # 24 tests
make lint        # ruff + tsc --noEmit
```

Coverage is deliberately weighted to the things that break demos:

- **Ingest** — every sample, title blocks, aliased columns, semicolon
  delimiters, missing columns, empty files, headerless junk
- **Scoring** — high-volume rule-bound work is autonomous; judgement work stays
  human however often it runs; PII caps; keyword rules do not leak from the
  process group name; weights sum to 1.0
- **DoD** — all five clauses asserted on a real run
- **Sanity** — all three bands represented; bridge arithmetic internally
  consistent; shares sum to 100%
- **Degradation** — an invalid API key still produces a complete blueprint

`test_all_three_bands_are_represented` is the useful canary. A run where
everything lands in one band means the policy pack is misconfigured, which is
exactly the bug this codebase shipped once already.

---

## Extending it

**A new industry.** Add an entry to `INDUSTRY_PACKS` in `policy.py`, a sample in
`mock-data/`, and an item to `INDUSTRIES` in `main.py`. No other change.

**A client-specific policy.** Drop `policy/<industry>.yaml`. It merges over the
base pack, so you can raise the autonomous bar or add a cap for one account
without touching code. See `backend/policy/README.md`.

**A new provider.** Implement `complete()` returning an `LLMResult`, register it
in `Router._build_provider`, add tier defaults to `PROVIDER_DEFAULTS`.

**LangGraph.** Reimplement `Pipeline.run` as a `StateGraph` over the same stage
functions, using `interrupt()` for the gate halt. Events and contracts unchanged.

**Postgres and pgvector.** Replace `TaskCache` with a pgvector-backed
implementation behind the same `lookup`/`put` interface, and persist `RUNS` and
`AUDIT`, which are in-memory today.

**The APQC master map.** To embed
[sillinous/apqc-pcf-master](https://github.com/sillinous/apqc-pcf-master) as the
taxonomy view, extract its node and flow data to JSON and re-render in the React
SVG layer, joining on category code. You keep its zoom, pan and minimap logic and
gain a shared selection state with the mesh. An iframe with `postMessage` is
faster to build but loses that. It is MIT licensed — attribute it in the
architecture slide and be clear about which parts you wrote.

---

## Known limits

Worth saying out loud rather than being caught on.

- **Runs are in memory.** A restart loses them. Fine for a demo, not for
  production — see the Postgres note above.
- **Residual factors are assumptions.** They are not measured from this client's
  data. Expose them and let people test them.
- **Volume data is required for a point estimate.** Without it, effort is a
  range, and the UI says so. If a client cannot supply volumes, present a range.
- **The cache uses token overlap, not embeddings.** Cheap and free, but it will
  miss paraphrases that share no vocabulary.
- **Cross-group dependency inference is heuristic.** It joins adjacent process
  groups in taxonomy order. Real dependency data from an APQC integration flow
  model would be better.
- **A large headcount shift is phased in reality.** The bridge shows an end
  state, not a schedule. Present it as three waves.

---

MIT licensed. Built for the FIFA AI Hackathon, August 2026.
