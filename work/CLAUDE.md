# CLAUDE.md — Virtual Room 6

## Project

Hackathon scenario 4: Data & Analytics — "40 Dashboards, One Metric, Four Answers"
Domain: SaaS / Subscription. Contested metric: Churn.

The goal is one authoritative churn definition, a calculation engine, a single dashboard, and optionally a natural-language query layer. Every calculated result must be tagged with the definition version that produced it.

## Team

- Kaushal, Nitu
- Dobrowolski, Jakub
- Gluszczak, Michal
- Lojewski, Krzysztof
- Mical, Jakub
- Singh, Tijender
- Wieczorek, Krzysztof
- Krauzewicz, Agata

## The Four Churn Definitions We Are Reconciling

| Name | What it counts | Downgrade | Clock starts |
|---|---|---|---|
| Logo Gross | Did the customer cancel? | No | End of contract |
| Revenue Gross | ARR lost to cancellation | No | End of contract |
| Revenue Net | ARR lost minus expansion | No | End of contract |
| Finance | ARR lost including downgrades | Yes | Last payment date |

Boundary examples and full edge-case table live in `definitions/churn_v1.md` (to be created).

## Conventions

- **Definition versioning:** every metric result carries a `definition_version` field (e.g. `churn_v1`). Never return a number without it.
- **No vague thresholds:** replace "recent", "significant", "material" with explicit numeric cutoffs. If unsure, ask.
- **Edge cases over happy path:** when writing tests, cover downgrades, partial shipments, mid-period plan changes, and grace-period customers first.
- **Refusals are first-class:** the NL query layer must refuse questions the data honestly can't answer. Refusal accuracy is tracked in the scorecard.

## Folder Structure (target)

```
definitions/        # churn_v1.md — the authoritative definition
data/               # synthetic SaaS subscription data (generated)
engine/             # calculation API — testable, versioned
dashboard/          # single replacement dashboard
reconciliation/     # edge-case table: our number vs. the four legacy calculations
scorecard/          # eval harness for NL queries, runs in CI
decisions/          # ADRs for key architectural choices
presentation.html   # HTML deck (built with Claude Code)
```

## Working Style

- Commit after each meaningful unit of work. The commit history is part of the submission.
- Update `README.md` challenge statuses as work progresses (`not started` → `in progress` → `done` / `partial`).
- For anything destructive or hard to reverse, confirm before executing.
- Prefer editing existing files over creating new ones.
- No comments that explain what the code does — only comments that explain why a non-obvious choice was made.

## Key Constraints

- No client or internal data. All data in this repo must be synthetic and safe to share.
- The reconciliation table (challenge 6) is the highest-priority artifact — it wins the room.
- The definition (challenge 3) must be locked before the engine (challenge 4) is built.

---

## Sky UK — Subscription Churn Dashboard

### Core KPIs

#### Volume & Base Metrics

| KPI | Definition |
|---|---|
| Total Active Subscribers | Live paying subs at point in time |
| Gross Adds | New subs acquired in period |
| Gross Churn | Subs cancelled in period (absolute) |
| Net Adds | Gross Adds minus Gross Churn |
| Churn Rate % | Churned / Active at start of period |
| Monthly Recurring Revenue (MRR) | Sum of all active sub values |
| MRR Churn % | Revenue lost to churn / MRR |

### By Product / Logo

| Product | Key Churn Drivers |
|---|---|
| Sky Glass / Sky Q (TV) | Contract end, price increases, streaming competition |
| Sky Broadband | Speed dissatisfaction, switching incentives |
| Sky Mobile | Network quality, handset deals |
| Sky Cinema / Sky Sports | Content calendar gaps, seasonal |
| NOW TV (streaming) | No contract — highest churn risk |
| Sky Protect (insurance) | Claims experience, renewal price shock |

Logo-level KPIs:
- Churn rate per product (monthly / quarterly)
- Average Revenue Per User (ARPU) by product
- Bundle penetration (multi-product subscribers churn ~3x less)
- Days to churn from last interaction

### By Volume Breakdown

- By region — NI, Scotland, Wales, England (regulatory + network variance)
- By acquisition channel — Direct, Retail, Telesales, Online, Partner
- By tenure cohort — 0–6m, 6–12m, 1–2yr, 2–5yr, 5yr+
- By contract type — In-contract vs. out-of-contract (OOC) vs. rolling monthly
- By bundle depth — Single product vs. double play vs. triple play

### By Start Date (Cohort Analysis)

| View | What it tells you |
|---|---|
| Cohort survival curve | % of a start-month cohort still active at M1, M3, M6, M12, M24 |
| Time-to-churn distribution | When do most cancellations happen? (First 90 days is often the peak) |
| OOC exposure curve | How many subs roll off contract each month over the next 12m |
| Vintage churn rate | Cohorts acquired via promo vs. full-price — do they behave differently? |

### Renewal Forecast

| Metric | Method |
|---|---|
| Contracts expiring (next 30/60/90d) | Pipeline from billing system |
| Predicted churn rate at renewal | ML propensity score (logistic regression or gradient boost on tenure, usage, NPS, price delta, interactions) |
| At-risk MRR | Expiring contracts × predicted churn % × ARPU |
| Save rate % | Retentions / total contacted |
| Retention offer cost | Discount given × saves |
| Net revenue retained | Saved MRR − offer cost |

### Dashboard Charts

1. **Churn Rate Trend — Line Chart**
   - Y: Monthly churn rate %; X: Month (rolling 13m)
   - Series: By product (TV, Broadband, Mobile, NOW)
   - Overlay: Industry benchmark line

2. **Cohort Survival Heatmap**
   - Rows: Acquisition month (Jan 24 → Dec 25); Columns: Month since acquisition (M0 → M24)
   - Cell value: % of cohort still active
   - Colour: Green (high retention) → Red (high churn)

3. **OOC Exposure — Stacked Bar**
   - X: Next 12 months; Y: Volume of subs coming off contract
   - Stack: By product; Overlay line: Predicted saves (propensity model)

4. **Churn by Tenure — Histogram**
   - X: Months since activation (bucketed); Y: Churn events
   - Shows: Bimodal peak at <3m (bad fit) and 12–14m (first renewal)

5. **MRR Waterfall — Monthly Bridge**
   - Start: Prior month MRR → +Gross adds MRR → −Churned MRR → ±Upgrades/Downgrades → End: Current month MRR

6. **At-Risk Subscriber Funnel**
   - Total OOC subs → Contacted → Engaged → Saved → Churned
   - Shows save rate and drop-off at each stage

7. **Churn Reason Pareto — Bar Chart**
   - Y: Cancellation reason (price, found better deal, financial hardship, moved, not using)
   - X: % of churn volume

8. **Propensity Score Distribution — Histogram**
   - X: Churn propensity score (0–1); Y: Subscriber count
   - Highlight: High-risk band (>0.7) with MRR value at risk
 