# Team "Virtual Room 6"

## Participants

| Name | Role |
|---|---|
| Kaushal, Nitu | PM / BA — stakeholder requirements |
| Dobrowolski, Jakub | Data Engineering — synthetic data generation |
| Gluszczak, Michal | Architecture — metric definition & API design |
| Lojewski, Krzysztof | Dev — FastAPI calculation engine |
| Mical, Jakub | Dev — dashboard frontend |
| Singh, Tijender | Quality — reconciliation & testing |
| Wieczorek, Krzysztof | Dev — data pipeline & tooling |
| Krauzewicz, Agata | Dev — presentation & integration |

---

## Scenario

**Scenario 4: Data & Analytics — "40 Dashboards, One Metric, Four Answers"**

**Domain:** Streaming / Subscription (Sky UK — logo-level subscriptions: Netflix, Disney+, HBO Max, Apple TV+, Amazon Prime Video, Paramount+, Hulu)

**Contested metric:** Churn — four stakeholder teams calculated it four different ways from the same data: Logo Gross (3.2%), Revenue Gross (4.7%), Revenue Net (2.1%), Finance (6.3%). Nobody trusted any of them.

---

## Road to the Goal

### Step 1 — Understand the conflict (Challenge 1: The Room)

We started by mapping the four competing churn definitions and the stakeholders behind them. The core disagreements:

- **Do downgrades count as churn?** Finance says yes (ARR is lost). Sales says no (the customer is still a customer).
- **When does the clock start?** Three teams use contract end date. Finance uses last payment date.
- **Do grace-period cancellations count?** Revenue Gross excludes them. Logo Gross counts them.
- **Does expansion offset cancellation?** Only Revenue Net offsets. Everyone else ignores it.

We captured these as explicit edge cases rather than smoothing them over — because the disagreement is the product.

### Step 2 — Lock the definition (Challenge 3: The Definition)

Before writing a line of code, we agreed on `churn_v1` as the authoritative definition:

- Clock starts at **end of contract** (not last payment)
- Grace period window: **≤ 14 calendar days** after contract end — flagged separately, counted
- Downgrade counted when ARR delta **> 10%** of prior MRR
- Expansion reported as a **separate metric**, not an offset
- Every result carries `definition_version: churn_v1` — no number without provenance

The definition lives in `CLAUDE.md` and is enforced at the API layer.

### Step 3 — Generate realistic data (Challenge 2: The Mess)

We generated 5,000 synthetic subscriber records (`data/subscriptions.csv`) with:

- History from **2019** so long-tenure cohorts (2–5yr, 5yr+) exist from day 1
- **7 streaming products** with real-world MRR ranges and published churn rates (Netflix ~2%/mo, Paramount+ ~5%/mo — Antenna/Kantar 2023–24)
- **Bimodal churn peaks**: M1–M2 (free-trial expiry) and M12–13 (annual renewal shock)
- Amazon Prime Video modelled as 98% rolling-monthly (Prime perk, no contracts)
- Realistic noise: plan upgrades/downgrades, grace-period cancellations, NPS influence on churn probability, bundle depth discounts (10%/18%)
- 30-day minimum billing cycle — zero M0 churn

### Step 4 — Build the calculation engine (Challenge 4: The Engine)

`engine/api.py` is a FastAPI service that reads `subscriptions.csv` and serves all dashboard metrics. Every response carries `definition_version`.

Key endpoints:

| Endpoint | What it returns |
|---|---|
| `GET /kpis/summary` | Top-level KPIs for any month |
| `GET /charts/churn-rate-trend` | Rolling 13-month churn % by product |
| `GET /charts/cohort-survival` | Retention % by acquisition cohort |
| `GET /charts/ooc-exposure` | Contracts expiring over next 12 months |
| `GET /charts/mrr-waterfall` | MRR bridge: start → adds → churn → plan changes → end |
| `GET /charts/churn-reasons` | Pareto of cancellation reasons |
| `GET /charts/at-risk-funnel` | OOC subscriber save funnel |
| `GET /breakdown/{dimension}` | Churn rate by product / region / channel / tenure |
| `GET /forecast/renewal` | Renewal pipeline + propensity-weighted at-risk MRR |

### Step 5 — Replace the 40 dashboards (Challenge 5: The One)

`dashboard/index.html` is a single self-contained dark-themed dashboard using Chart.js. It calls the FastAPI backend and renders:

1. KPI strip (active subs, gross adds, churn rate, MRR, MRR churn %)
2. Churn rate trend — 13-month line chart by product
3. Cohort survival heatmap
4. OOC exposure stacked bar (next 12 months)
5. Churn by tenure histogram
6. MRR waterfall bridge
7. At-risk subscriber funnel
8. Churn reason Pareto
9. Propensity score distribution

### Step 6 — Win the room (Challenge 6: The Reconciliation)

The reconciliation table in `presentation.html` (slide 6) shows the same six edge cases evaluated by all four legacy definitions and `churn_v1` side by side. It makes the disagreement explicit and shows exactly where `churn_v1` takes a principled position.

### Step 7 — Tell the story (Presentation)

`presentation.html` is a 9-slide self-contained HTML deck covering the full narrative: problem (40 dashboards, 4 answers), persona (Sarah, account manager), logo subscription view, signal intelligence, the reconciliation, example charts, and the unified metric conclusion.

---

## What We Built

| Artifact | Status | Notes |
|---|---|---|
| Churn definition `churn_v1` | **done** | Locked in `CLAUDE.md`, enforced in API |
| Synthetic data — 5,000 subscribers | **done** | `data/subscriptions.csv`, generated by `data/generate.py` |
| FastAPI calculation engine | **done** | `engine/api.py`, 12 endpoints, all versioned |
| Single replacement dashboard | **done** | `dashboard/index.html`, 9 charts, calls live API |
| Pitch presentation | **done** | `presentation.html`, 9 slides, self-contained |
| Reconciliation table | **partial** | Covered in presentation; standalone `reconciliation/` folder not built |
| NL query layer | **not started** | Stretch goal (Challenge 8) |
| Eval scorecard | **not started** | Stretch goal (Challenge 7) |
| Agentic variance panel | **not started** | Stretch goal (Challenge 9) |

## Challenges Attempted

| # | Challenge | Status | Notes |
|---|---|---|---|
| 1 | The Room | **done** | Four stakeholder definitions mapped and conflict documented |
| 2 | The Mess | **done** | 5,000-row synthetic dataset with realistic noise and industry-calibrated churn rates |
| 3 | The Definition | **done** | `churn_v1` locked with explicit thresholds and edge cases |
| 4 | The Engine | **done** | FastAPI service, 12 endpoints, every response versioned |
| 5 | The One | **done** | Single dashboard replacing 40, 9 chart types |
| 6 | The Reconciliation | **partial** | In presentation; full standalone table not built |
| 7 | The Scorecard | not started | |
| 8 | The Question | not started | |
| 9 | The Panel | not started | |

---

## Key Decisions

**1. Lock the definition before writing code.**
We wrote `churn_v1` in prose (in `CLAUDE.md`) before any SQL or Python. Every subsequent decision — data schema, API response shape, dashboard labels — derived from it. This prevented the most common failure mode: code that embeds undocumented assumptions.

**2. Tag every result with `definition_version`.**
No endpoint returns a churn number without `"definition_version": "churn_v1"`. When the definition eventually changes, the version bumps and historical results stay queryable without confusion.

**3. Replace vague thresholds with explicit numbers.**
"Recent" → 14 calendar days. "Significant downgrade" → ARR delta > 10%. "Material churn" → > 0.5% of active base. Every cut-off is in the definition file, not buried in a WHERE clause.

**4. Model Amazon Prime Video as rolling-monthly.**
Prime Video is a perk of Amazon Prime, not a standalone subscription. Treating it like a contracted service would have inflated OOC exposure numbers. 98% rolling-monthly is the correct model.

**5. Start history in 2019.**
A dataset that starts in 2021 has no 5yr+ cohort and a sparse 2–5yr cohort — making the survival curves useless for retention analysis. Extending history to 2019 gave us a realistic established base from the dashboard's first rendered month.

**6. Reconciliation table as the centrepiece.**
Per the scenario brief, "this is the artifact that wins the room." We prioritised the reconciliation slide over dashboard polish. The six edge-case rows — one for each major disagreement — are what Agata (or Sarah) puts in front of the VP.

---

## How to Run It

Assumes Python 3.10+ installed. No Docker required.

```bash
# Install dependencies
pip install fastapi uvicorn pandas

# Start the API
cd work
uvicorn engine.api:app --reload --port 8000

# Open the dashboard (in a browser)
open dashboard/index.html   # or double-click

# Open the presentation (in a browser)
open presentation.html      # or double-click
```

The dashboard fetches from `http://localhost:8000` by default. The presentation is fully self-contained and works offline.

To regenerate the synthetic data:

```bash
cd work
python data/generate.py
# Outputs work/data/subscriptions.csv (5,000 rows)
```

---

## If We Had More Time

1. **Challenge 6 — standalone reconciliation folder** with a proper edge-case table as a machine-readable artifact (not just a slide), so it can be diffed when `churn_v1` becomes `churn_v2`.
2. **Challenge 7 — eval scorecard** with a golden set of NL queries including deliberate refusals, running in CI so quality numbers move with every definition change.
3. **Challenge 8 — NL query layer** over an MCP server (`get_metric`, `list_definitions`, `explain_calculation`, `compare_periods`), with few-shot refusal examples baked in.
4. **Challenge 9 — agentic variance panel** using Task subagents: one segments by geography, one by product, one by tenure. Coordinator picks the best explanation and shows the losing theories rather than hiding them.
5. **Definitions folder** — `definitions/churn_v1.md` as a first-class versioned document, separate from `CLAUDE.md`, with a changelog.

---

## How We Used Claude Code

**What worked best:**
- Generating the synthetic data generator (`generate.py`) from a prose spec in `CLAUDE.md` — Claude translated the industry constraints (bimodal churn, Amazon Prime behaviour, contract-type weights) directly into correct Python, first pass.
- Scaffolding the FastAPI engine from the list of dashboard charts — each endpoint was generated with the right response shape and `definition_version` baked in from the start.
- The presentation HTML — 9-slide self-contained deck built from a bullet-point brief in a single generation.

**What surprised us:**
- Claude Code correctly modelled the Amazon Prime rolling-monthly edge case without being told explicitly — it inferred from the domain description that Prime Video is a Prime perk, not a standalone service.
- The floating-bar waterfall chart in Chart.js was generated correctly on the first attempt, including the transparent base dataset trick.

**Where it saved the most time:**
- The data calibration pass (commit `4815a2e`) — updating 7 products' churn rates, MRR ranges, contract-type weights, and churn reason distributions to match published industry figures took minutes rather than hours of manual lookup and coding.
- Keeping `definition_version` consistent across every API response and every slide label without needing to chase it down manually.
