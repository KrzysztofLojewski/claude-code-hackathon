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
 