# Build prompt: Forecast Model Arena (model benchmarking UI)

Paste everything below the line into Claude Code (Opus) at the root of the S&OP Workbench repo. **Also copy `arena-reference.html` into the repo** (e.g. `docs/reference/arena-reference.html`) — it's the working prototype this prompt describes, including the battle log, lenses, and click-to-interrogate interaction. Open it in a browser first. Claude Code must port its visuals, animation and every interaction, not re-imagine them.

---

## Goal

Add a **Forecast Model Arena** to the S&OP Workbench: a canvas-based orbital simulation where each forecasting method lives as a glowing orb, sized by accuracy (bigger = lower WAPE), positioned by whichever *lens* the user has selected, and animated across six rolling-origin backtest rounds driven by the app's real per-method WAPE. It must look and behave like `docs/reference/arena-reference.html` — study that file first, it is the spec for the canvas stage, lens projections, orb rendering, battle log, standings board, and click-through detail panel.

This page fulfills the DoD criterion: **"add model benchmarking across multiple forecast methods under identical data, hardware and evaluation criteria."** Every number shown comes from real backtests, not hardcoded mock data.

---

## 0. Methods roster — 15 forecast methods + Champion routing

The arena must benchmark exactly these 15 methods plus the Champion routing meta-strategy. Every one of them must be implemented and run through the same rolling-origin backtest harness before the arena can display real numbers.

| # | Method | `kind` tag | Notes |
|---|--------|-----------|-------|
| 1 | Seasonal naïve | `naive` | Last-year repeat baseline |
| 2 | Moving average | `naive` | Simple / weighted MA baseline |
| 3 | ETS / Holt-Winters | `stat` | Exponential smoothing family |
| 4 | ARIMA / SARIMA | `stat` | Box-Jenkins with seasonal differencing |
| 5 | SARIMAX | `stat` | ARIMA + exogenous regressors (promotions, price, etc.) |
| 6 | TBATS | `stat` | Trigonometric seasonality, Box-Cox, ARMA errors |
| 7 | Prophet | `stat` | Facebook/Meta decomposition model |
| 8 | Theta method | `stat` | Assimakopoulos-Nikolopoulos decomposition |
| 9 | LightGBM / XGBoost | `ml` | Global gradient-boosted tree model |
| 10 | Quantile GBM | `ml` | Probabilistic gradient-boosted model |
| 11 | DeepAR | `dl` | Amazon autoregressive RNN |
| 12 | N-BEATS | `dl` | Pure DL interpretable basis expansion |
| 13 | TFT (Temporal Fusion Transformer) | `dl` | Attention-based with static covariates |
| 14 | N-HiTS | `dl` | Multi-rate hierarchical interpolation |
| 15 | TimesFM (zero-shot) | `found` | Foundation model — zero-shot, no fine-tuning |
| — | Champion routing | `route` | Per-family best, meta-strategy |

`kind` drives the orb color via a shared palette:
```js
const PAL = {
  naive: '#8C98AC',   // grey
  stat:  '#2a78d6',   // blue
  ml:    '#eb6834',   // orange
  dl:    '#4a3aa7',   // purple
  found: '#e87ba4',   // pink
  route: '#eda100'    // gold
};
```

## 1. Data the arena needs (build or reuse)

If the model-benchmarking backtest harness doesn't exist yet, build the minimum needed to drive this UI honestly — don't fabricate the numbers behind it.

Create one endpoint, `GET /api/benchmark/arena`, returning:

```ts
{
  methods: [{
    id: string,            // e.g. 'nbeats', 'ets', 'lgbm'
    name: string,          // display name
    kind: 'naive'|'stat'|'ml'|'dl'|'found'|'route',
    runtime: number|'mixed',  // seconds per product-family run (mixed for routing)
    cost: number              // $/run
  }],
  rounds: 6,
  scoredFromRound: 4,           // first round scored on truly held-out data
  seriesCount: number,          // total series benchmarked (e.g. 3,240)
  wape: {                       // [methodId] -> [wape_round1 ... wape_round6]
    [methodId]: number[]
  },
  bias: {                       // [methodId] -> { near: number, far: number }
    [methodId]: { near: number, far: number }   // % bias at near vs far horizon
  },
  familyWins: {                 // [methodId] -> string[]  (product families this method wins)
    [methodId]: string[]
  },
  h2h: {                        // [methodA][methodB] -> { p, sig, winner }
    [methodId]: {
      [methodId]: {
        p: number,              // Diebold-Mariano p-value
        sig: boolean,           // p < 0.05
        winner: string|null     // method id, or null if tied
      }
    }
  }
}
```

Where every value comes from a real rolling-origin backtest run, not synthesized:
- **methods:** every forecasting method actually implemented and run under identical conditions (see the "Held equal" bar in the reference — same series set, same 104-wk history window, same container class, same 13-wk horizon).
- **wape:** the method's actual WAPE for each rolling-origin round. 6 rounds total, rounds 4–6 scored on held-out data.
- **bias:** directional forecast error at near-horizon (weeks 1–4) and far-horizon (weeks 10–13).
- **h2h:** results of Diebold-Mariano tests between every pair of methods, run on the actual per-series error arrays. **Do not use the toy `p = exp(-gap*k)` placeholder from the reference** — that was a stand-in for a real statistical test.
- **familyWins:** which product families each method is champion of (lowest WAPE with significance).

## 2. Where it goes in the UI

New sidebar item **Model Arena** (after Audit Trail), matching the reference's page chrome (crumb reading "Forecast benchmark · demand forecasting · N series · 15 methods", the "Held equal" bar, the heading card). Reuse the app's existing sidebar, tokens and fonts — don't rebuild the shell.

## 3. Canvas stage — port from the reference

The arena renders on an HTML5 Canvas element (1180×560 logical, scaled to DPR for retina) with DOM overlays for text labels (text stays crisp at any zoom).

### 3.1 Background
- Dark radial gradient: `radial-gradient(circle at 30% 20%, #0F1E3D, #0A1730 62%, #08122A)`
- Subtle grid lines: `rgba(143,180,255,0.06)`, 8 vertical × 6 horizontal
- When in Bias map lens: centered crosshair with dashed lines and "unbiased" label

### 3.2 Orbs
Each method is one orb. Drawing order per orb:
1. **Outer glow** — radial gradient from `color+55` to `color+00`, radius = `orb_radius × 2.6`
2. **Pulsing scoring ring** — `sin(t * 0.004 + phase)` drives radius oscillation; `color+88` stroke
3. **Hub fill** — solid circle at `orb_radius`
4. **Champion routing** gets a dashed white border ring: `setLineDash([3,3])`, radius = `orb_radius + 4`
5. **Selection ring** — solid white, radius = `orb_radius + 8`, drawn when selected
6. **Hover ring** — semi-transparent white, radius = `orb_radius + 6`
7. **Label** — method name + WAPE% below the orb, IBM Plex Sans/Mono

### 3.3 Orb sizing
`radius = 9 + ((19 - wape) / 10) × 18` — bigger orb = lower (better) WAPE, clamped 9..27px.

### 3.4 Significance threads
Lines drawn between orb pairs where the DM test is significant (p<0.05). In the Significance lens, all significant threads are drawn faintly; when an orb is selected, only its threads are drawn brighter. In other lenses, threads appear only for the selected orb.

### 3.5 Collision resolution
With 16 orbs, labels overlap without physics. Port the `resolveCollisions()` function from the reference:
- Works in pixel space after lens projection
- 4 iterations per frame
- Minimum clearance = `radius_a + radius_b + 34px` (label space)
- Pushes overlapping pairs apart equally
- Clamps to stage bounds after resolution
- Orb positions ease toward lens targets with `+= (target - current) × 0.06` plus small idle drift (`sin(t * 0.0011 + phase) × 0.006`)

### 3.6 Seeded PRNG
Use a seeded mulberry32-style RNG (`rng(90210)`) for deterministic idle drift, so the layout is reproducible across reloads.

## 4. Lens system — 4 projections of the same population

The lens bar sits top-right of the stage. Each lens re-projects all orbs onto different [x, y] coordinates in 0..1 space. **Port all four exactly from the reference:**

| Lens | X axis | Y axis | Purpose |
|------|--------|--------|---------|
| **Overview** | Runtime (log scale: `1 - ln(rt+1)/ln(56)`) | Accuracy (WAPE) | Cost vs. accuracy trade-off |
| **Significance** | H2H win rate (wins / max(total_sig_matchups, 4)) | Accuracy | Who actually beats whom |
| **Bias map** | Near-horizon bias (-% to +%) | Far-horizon bias (-% to +%) | Directional error profile |
| **Plan impact** | Downstream margin estimate | Accuracy | Business value |

Axis labels update when the lens switches (see `axL`, `axR`, `axT` elements in the reference). The Bias map lens adds the centered crosshair.

## 5. Round scrubber and autoplay

- Scrubber range 0..1000, mapped to rounds 1..6
- Autoplay at ~0.045 units per ms frame delta (same pacing as the reference, ~1.9s per round)
- Scrubber is draggable (pauses autoplay when dragged)
- Play/pause button with SVG icon toggle
- Phase indicator: "Round **N** of 6 · training window" for rounds 1–3, "scored round (held out)" for rounds 4–6
- Round label: "Round N · wk W" where `W = 67 + (round-1) × 8`, with " · scored" suffix for scored rounds
- Each method's WAPE updates per round: `wape[methodId][round-1]`
- Orb sizes animate as WAPE changes

## 6. Pointer interaction — clicking an orb

Same as the reference:
- **Hover:** cursor pointer, semi-transparent ring, tooltip-like highlighting
- **Click:** selects the orb (toggles if already selected), pauses autoplay, opens the **detail panel** (replacing the log/standings tabs)

### 6.1 Detail panel contents (port from the reference exactly):
- **Header:** colored dot + method name, kind label beneath (e.g. "Statistical / classical", "Deep learning", "Meta-strategy · routes per product family")
- **Stat grid** (2×2): WAPE at current round, Runtime, Near-horizon bias, Far-horizon bias
- **Head-to-head rivals** (top 6 by significance): each row shows rival name with dot, colored p-value badge (win/loss/tie)
- **Product-family wins:** badge list of families this method is champion of
- **Plan interpretation:** contextual sentence about what this method's performance means for production routing
- **← Back to battle log** link at the bottom to return to log/standings view

## 7. Battle log — the part that must not change

**Keep the battle log exactly as in the reference — this is a hard requirement, not a suggestion.**

### 7.1 How it works
The log shows a curated set of **marquee match-ups** (key head-to-head pairs), each revealed the round its Diebold-Mariano result first clears p<0.05. This models statistical power growing with more backtest rounds.

- Each entry shows: round tag (`R1`…`R6`), the winning method (colored by kind), the losing method, and the DM p-value
- Ties (p≥0.05 even at round 6) show as "remains a **statistical tie**"
- The log accumulates as the round scrubber advances (entries for rounds beyond the current scrub position are not shown)
- Clicking a log entry selects that method's orb and opens its detail panel

### 7.2 Round-aware reveal logic
The reference uses a `pAtRound(pFinal, r)` function to model how the p-value decreases (evidence strengthens) as more backtest rounds complete:
```js
function pAtRound(pFinal, r) {
  return Math.min(0.97, Math.pow(pFinal, Math.sqrt(r / 6)));
}
```
For the real implementation: replace this heuristic with the actual per-round DM test results from the backtest harness. If per-round DM tests are available from the API, use those directly. If not, the `pAtRound` formula is an acceptable stand-in, but note it in a code comment.

### 7.3 Marquee match-ups
The reference defines ~27 curated pairs for the 15-method roster:
- Champion routing vs every major method (routing vs N-HiTS, N-BEATS, TFT, DeepAR, LightGBM, TimesFM, ETS, Quantile GBM, SARIMAX, Seasonal naïve)
- Key within-class pairs: N-HiTS vs N-BEATS, N-BEATS vs TFT, N-BEATS vs DeepAR, TFT vs DeepAR, LightGBM vs Quantile GBM, ETS vs ARIMA, ETS vs SARIMAX, ETS vs TBATS, ARIMA vs SARIMAX, Theta vs ETS, Moving average vs Seasonal naïve, Prophet vs TBATS
- Cross-class upset candidates: TimesFM vs N-BEATS, TimesFM vs N-HiTS, N-HiTS vs LightGBM, TFT vs LightGBM, DeepAR vs TimesFM

For the real build: the marquee set should include every pair where the final DM test is significant plus a curated selection of interesting ties.

**Do not redesign the log into a different shape** (no grouping by method, no collapsing rounds, no summarizing) — the point is that a judge can watch it fill in round by round and trust every line maps to a real statistical test.

## 8. Standings tab (alongside the battle log)

The **Standings** tab sits alongside the Battle log as a second view of the same right-hand panel, switchable via tabs. It shows all methods ranked by current-round WAPE:
- Each row: rank number, method name, horizontal bar (colored by kind), WAPE% value
- Bar width scales between `best_wape` and `worst_wape` across the roster
- Live-updates as the round scrubber moves
- Exactly as in the reference — don't merge it into the log or drop it

## 9. Stat tiles and page layout

### 9.1 "Held equal" conditions bar
Dark navy bar (`#0F1B33`) with 4 columns:
- **Data:** Same N series, same 104-wk history, same holdout windows
- **Hardware:** Same container class, 8 vCPU / 32GB, no GPU methods favored
- **Evaluation:** 6 rolling origins, 13-wk horizon, rounds 4–6 scored blind
- **Significance:** Diebold-Mariano test on every head-to-head, not just averages

### 9.2 Heading card
- Title: **"Model benchmarking, run live — not a static leaderboard"**
- Subtitle: explains the DoD criterion, rolling-origin scoring, and the four lenses

### 9.3 Footer bar
- "Reading the arena:" explainer (orb size = accuracy, position = lens, threads = significance, pulsing ring = actively scored)
- Recommendation badges: "⬤ Champion routing", "Lead with: Significance lens"

### 9.4 Layout
- Arena stage (canvas + overlays) takes the left ~75%
- Right panel (320px) holds the tab bar (Battle log / Standings) and the detail view
- Grid: `grid-template-columns: minmax(0, 1fr) 320px`

## 10. Design tokens (match the reference)

```css
--bg: #F3F5F9;  --card: #ffffff;  --line: #E1E6EE;  --text: #16213B;
--muted: #5B6B82;  --faint: #8C98AC;  --blue: #2F6FEB;
--side: #0E1A33;  --side-2: #18284A;
```
- Font: IBM Plex Sans (body) + IBM Plex Mono (numbers, labels, badges)
- Border radius: 12px cards, 8px stat boxes, 20px lens buttons
- Sidebar: 214px, dark navy with active highlight

## 11. Accessibility

- `prefers-reduced-motion: reduce` → disable idle drift and pulse animations, use `setInterval` fallback at 700ms for position updates
- All orbs reachable by keyboard (tab focus, Enter to select)
- Color is never the only differentiator — kind labels and text accompany every colored element

## 12. Rules

- Every WAPE, bias, runtime, p-value, and family win shown comes from `/api/benchmark/arena`. No hard-coded demo values in the component. Delete the reference's seeded-random data generator once the endpoints are wired.
- Keep the DM test computation server-side or in a shared, tested module — don't run significance testing in the browser against raw series data.
- The canvas renders at the device pixel ratio (DPR-scaled) for crisp visuals on retina displays.
- Must render correctly in the app's light theme and at the same width as other pages.
- Respect the app's existing IBM Plex Sans / IBM Plex Mono font setup — don't add duplicate font loads.

## 13. Done when

- [ ] The arena loads real per-method WAPE from the last completed benchmark run and matches the reference's look side-by-side.
- [ ] All 15 methods + Champion routing appear as orbs with correct kind colors and sizing.
- [ ] Switching lenses re-projects the orbs correctly for all 4 lenses (Overview, Significance, Bias map, Plan impact).
- [ ] Scrubbing rounds 1→6 visibly changes orb sizes as WAPE evolves, and the round indicator / phase description update.
- [ ] The battle log fills in round-by-round with real DM p-values, and clicking a log entry opens the corresponding method's detail panel.
- [ ] The Standings tab agrees with the live WAPE values at every scrub position.
- [ ] Clicking an orb opens the detail panel with correct stats, head-to-head rivals, family wins, and plan interpretation.
- [ ] Significance threads (connecting lines) draw only between pairs where p<0.05.
- [ ] Collision resolution prevents label overlap with 16 orbs in all lens views.
- [ ] `prefers-reduced-motion` is respected.
- [ ] Finish with a short summary of files changed, which endpoints are new, and anything you couldn't wire to a real backtest (e.g. if per-method bias isn't tracked yet and had to be added).
