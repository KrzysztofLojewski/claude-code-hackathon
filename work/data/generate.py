"""
Generates synthetic streaming subscriber data for the churn dashboard.
Covers: cohort survival, OOC exposure, MRR waterfall, churn by tenure,
propensity scores, churn reasons, and all volume breakdown dimensions.

Realism notes:
- History starts 2021-01 so 2-5yr tenure cohorts exist
- Pre-existing base of ~800 subs seeded before 2021 to avoid greenfield start
- No churn in month 0 (30-day minimum billing cycle)
- Monthly base churn rates calibrated to published industry figures
- Bundle subscribers pay a per-service discount (not uplift)
- Amazon Prime Video is almost entirely rolling-monthly (Prime perk)
"""

import csv
import random
import math
from datetime import date, timedelta
from collections import Counter

random.seed(42)

PRODUCTS = [
    "Netflix",
    "Disney+",
    "HBO Max",
    "Apple TV+",
    "Amazon Prime Video",
    "Paramount+",
    "Hulu",
]

REGIONS = ["England", "Scotland", "Wales", "NI"]
REGION_WEIGHTS = [0.84, 0.08, 0.05, 0.03]

CHANNELS = ["Online", "Telesales", "Direct", "Retail", "Partner"]
CHANNEL_WEIGHTS = [0.35, 0.25, 0.20, 0.15, 0.05]

CHURN_REASONS = [
    "price",
    "found_better_deal",
    "financial_hardship",
    "moved",
    "not_using",
]

CONTRACT_TYPES = ["in-contract", "OOC", "rolling-monthly"]

# Real-world monthly pricing (USD, standard/ad-free tiers)
PRODUCT_MRR = {
    "Netflix":             (15.49, 22.99),  # Standard → Premium
    "Disney+":             (7.99,  13.99),  # Basic → Premium
    "HBO Max":             (9.99,  15.99),  # With Ads → Ad-Free
    "Apple TV+":           (9.99,   9.99),  # Single flat price
    "Amazon Prime Video":  (8.99,   8.99),  # Included with Prime
    "Paramount+":          (5.99,  11.99),  # Essential → Showtime
    "Hulu":                (7.99,  17.99),  # With Ads → No Ads
}

# Monthly base churn rates — calibrated to public industry data
# Antenna/Kantar 2023-2024 averages for US/UK streaming
PRODUCT_BASE_CHURN = {
    "Netflix":             0.020,  # ~2%/mo, lowest churn in industry
    "Disney+":             0.035,  # ~3.5%/mo, volatile after price hikes
    "HBO Max":             0.030,  # ~3%/mo, strong content but expensive
    "Apple TV+":           0.040,  # ~4%/mo, thin content library
    "Amazon Prime Video":  0.015,  # ~1.5%/mo, sticky via Prime ecosystem
    "Paramount+":          0.050,  # ~5%/mo, highest churn in tier
    "Hulu":                0.032,  # ~3.2%/mo, mid-tier
}

# History extends to Jan 2021 so long-tenure cohorts exist
HISTORY_START = date(2021, 1, 1)
SIM_START     = date(2021, 1, 1)   # acquisition can begin here
SIM_END       = date(2026, 4, 1)   # ~63 months of history

# Total subscribers to generate (includes pre-existing base)
N_SUBSCRIBERS = 5000


def weighted_choice(options, weights):
    r = random.random()
    cumulative = 0.0
    for o, w in zip(options, weights):
        cumulative += w
        if r < cumulative:
            return o
    return options[-1]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(0, delta)))


def months_between(d1: date, d2: date) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def churn_prob_for_month(tenure_days: int, base_p: float,
                          contract_type: str, bundle_depth: str,
                          nps: int) -> float:
    # No churn in first 30 days — minimum billing cycle before cancellation possible
    if tenure_days < 30:
        return 0.0
    tenure_months = tenure_days // 30

    p = base_p

    # Bimodal tenure effect
    # Peak at M1-M2 (early bad fit / free trial expiry)
    if tenure_months == 1:
        p *= 2.8
    elif tenure_months == 2:
        p *= 1.8
    elif tenure_months == 3:
        p *= 1.3
    # Second peak at 12-13m (first annual renewal / price shock)
    elif 12 <= tenure_months <= 13:
        p *= 1.6
    # Loyal long-tenure subscribers churn less
    elif tenure_months >= 36:
        p *= 0.6
    elif tenure_months >= 24:
        p *= 0.75

    # Contract type — rolling-monthly is baseline for streaming
    # OOC only applies to the handful with annual contracts that have expired
    if contract_type == "OOC":
        p *= 1.7   # renewal decision point
    elif contract_type == "in-contract":
        p *= 0.4   # locked in, very hard to churn

    # Bundle effect: multi-service subscribers churn significantly less
    # (switching cost, convenience) — not a pricing discount in this model
    if bundle_depth == "double":
        p *= 0.65
    elif bundle_depth == "triple":
        p *= 0.38

    # NPS influence — detractors (0-6) churn more, promoters (9-10) churn less
    if nps <= 4:
        p *= 1.5
    elif nps <= 6:
        p *= 1.15
    elif nps >= 9:
        p *= 0.65

    return min(p, 0.40)


# ---------------------------------------------------------------------------
# Acquisition date distribution
# Earlier cohorts are more numerous (established base), recent cohorts smaller
# Weight: inversely proportional to how far from SIM_END the start is
# ---------------------------------------------------------------------------

def sample_acq_date() -> date:
    """
    Weight acquisition toward earlier dates to simulate an established business.
    Pre-2021 subs form the initial base visible on the dashboard from day 1.
    """
    year_weights = {2019: 0.08, 2020: 0.14, 2021: 0.22, 2022: 0.20, 2023: 0.18, 2024: 0.13, 2025: 0.05}
    yr = weighted_choice(list(year_weights.keys()), list(year_weights.values()))
    mo = random.randint(1, 12)
    day = random.randint(1, 28)
    return date(yr, mo, day)


rows = []

for sub_id in range(1, N_SUBSCRIBERS + 1):
    product = weighted_choice(
        PRODUCTS,
        # Approximate UK market share weights
        [0.30, 0.15, 0.12, 0.08, 0.20, 0.07, 0.08],
    )
    region  = weighted_choice(REGIONS, REGION_WEIGHTS)
    channel = weighted_choice(CHANNELS, CHANNEL_WEIGHTS)
    acq_date = sample_acq_date()

    # Contract type
    # All streaming is rolling-monthly except the small % who took annual plans
    if product == "Amazon Prime Video":
        # Prime is bundled — essentially always rolling-monthly
        contract_type = weighted_choice(CONTRACT_TYPES, [0.00, 0.02, 0.98])
    elif product in ("Netflix", "Disney+", "Apple TV+", "Paramount+", "Hulu"):
        # Streaming: ~10% took annual (in-contract), ~5% lapsed annual (OOC)
        contract_type = weighted_choice(CONTRACT_TYPES, [0.10, 0.05, 0.85])
    else:
        # HBO Max: slightly more annual plans due to bundle deals
        contract_type = weighted_choice(CONTRACT_TYPES, [0.18, 0.07, 0.75])

    contract_length_months = 0
    if contract_type == "in-contract":
        contract_length_months = random.choice([12, 12, 12, 24])  # mostly annual
    elif contract_type == "OOC":
        contract_length_months = 12  # annual that has expired

    contract_end_date = None
    if contract_type == "in-contract":
        contract_end_date = acq_date + timedelta(days=contract_length_months * 30)
    elif contract_type == "OOC":
        months_ago = random.randint(1, min(18, months_between(SIM_START, SIM_END) - 1))
        contract_end_date = SIM_END - timedelta(days=months_ago * 30)

    # Bundle depth
    bundle_depth = weighted_choice(
        ["single", "double", "triple"], [0.58, 0.30, 0.12]
    )

    # MRR — bundles get a per-service discount (reflect real bundle pricing)
    mrr_lo, mrr_hi = PRODUCT_MRR[product]
    base_mrr = round(random.uniform(mrr_lo, mrr_hi), 2)
    if bundle_depth == "double":
        base_mrr = round(base_mrr * 0.90, 2)   # 10% discount
    elif bundle_depth == "triple":
        base_mrr = round(base_mrr * 0.82, 2)   # 18% discount

    # NPS — right-skewed (more promoters than detractors, as in most streaming)
    nps = random.choices(range(0, 11), weights=[1, 1, 2, 3, 4, 6, 8, 12, 18, 20, 25])[0]

    # Simulate month-by-month churn
    base_p      = PRODUCT_BASE_CHURN[product]
    churn_date  = None
    plan_change = "none"

    current_month = date(acq_date.year, acq_date.month, 1)
    tenure_months = 0

    while current_month < SIM_END:
        tenure_days = (current_month - acq_date).days
        p = churn_prob_for_month(tenure_days, base_p, contract_type, bundle_depth, nps)

        if random.random() < p:
            # Churn falls on a random day in this month (after the 30-day mark)
            earliest = max(current_month, acq_date + timedelta(days=30))
            month_end = min(
                date(current_month.year, current_month.month, 28),
                SIM_END - timedelta(days=1),
            )
            if earliest <= month_end:
                churn_date = random_date(earliest, month_end)
                break

        # Occasional plan change after 6 months
        if plan_change == "none" and tenure_months > 6 and random.random() < 0.012:
            plan_change = random.choice(["upgrade", "downgrade"])
            if plan_change == "upgrade":
                base_mrr = round(base_mrr * random.uniform(1.10, 1.25), 2)
            else:
                base_mrr = round(base_mrr * random.uniform(0.70, 0.92), 2)

        # Advance to next month
        next_mo = current_month.month % 12 + 1
        next_yr = current_month.year + (1 if current_month.month == 12 else 0)
        current_month = date(next_yr, next_mo, 1)
        tenure_months += 1

    status = "churned" if churn_date else "active"

    # Churn reason — product-specific distributions
    churn_reason = None
    if status == "churned":
        if product in ("Disney+", "Apple TV+", "Paramount+"):
            # Content-gap services: not_using and found_better_deal dominate
            reason_weights = [0.20, 0.22, 0.13, 0.08, 0.37]
        elif product == "Amazon Prime Video":
            # Prime cancellations are mostly price (full Prime cost) or moving
            reason_weights = [0.40, 0.15, 0.25, 0.12, 0.08]
        else:
            # Netflix/HBO Max/Hulu: price increases are top driver
            reason_weights = [0.38, 0.22, 0.18, 0.10, 0.12]
        churn_reason = weighted_choice(CHURN_REASONS, reason_weights)

    # Propensity score
    # Churned subs get a high score (retrospective); active subs get model score
    if status == "churned":
        propensity_score = round(random.betavariate(5, 2), 3)   # skewed high
    else:
        propensity_score = round(random.betavariate(1.5, 7), 3) # skewed low

    # Tenure cohort
    tenure_months_at_end = months_between(acq_date, churn_date or SIM_END)
    if tenure_months_at_end < 6:
        tenure_cohort = "0-6m"
    elif tenure_months_at_end < 12:
        tenure_cohort = "6-12m"
    elif tenure_months_at_end < 24:
        tenure_cohort = "1-2yr"
    elif tenure_months_at_end < 60:
        tenure_cohort = "2-5yr"
    else:
        tenure_cohort = "5yr+"

    # Last interaction date
    if status == "active":
        last_interaction = SIM_END - timedelta(days=random.randint(0, 120))
    else:
        last_interaction = churn_date - timedelta(days=random.randint(1, 60))

    days_to_churn = (churn_date - last_interaction).days if churn_date else None

    # Grace period: churned within 14 days of contract end
    grace_period = False
    if churn_date and contract_end_date:
        grace_period = abs((churn_date - contract_end_date).days) <= 14

    rows.append({
        "subscriber_id":         f"STR-{sub_id:05d}",
        "product":               product,
        "region":                region,
        "acquisition_channel":   channel,
        "start_date":            acq_date.isoformat(),
        "contract_type":         contract_type,
        "contract_end_date":     contract_end_date.isoformat() if contract_end_date else "",
        "bundle_depth":          bundle_depth,
        "mrr":                   base_mrr,
        "nps_score":             nps,
        "status":                status,
        "churn_date":            churn_date.isoformat() if churn_date else "",
        "churn_reason":          churn_reason or "",
        "plan_change":           plan_change,
        "propensity_score":      propensity_score,
        "tenure_months":         tenure_months_at_end,
        "tenure_cohort":         tenure_cohort,
        "last_interaction_date": last_interaction.isoformat(),
        "days_to_churn":         days_to_churn if days_to_churn is not None else "",
        "grace_period":          str(grace_period).lower(),
    })

# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------
out_path = "/root/claude-bootcamp-setup/claude-code-hackathon/work/data/subscriptions.csv"
fieldnames = list(rows[0].keys())

with open(out_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------
total   = len(rows)
churned = sum(1 for r in rows if r["status"] == "churned")
active  = total - churned

print(f"Rows:    {total}")
print(f"Active:  {active}  ({active/total*100:.1f}%)")
print(f"Churned: {churned} ({churned/total*100:.1f}%)")

print("\nChurn rate by product:")
by_prod = {}
for r in rows:
    by_prod.setdefault(r["product"], {"total": 0, "churned": 0})
    by_prod[r["product"]]["total"] += 1
    if r["status"] == "churned":
        by_prod[r["product"]]["churned"] += 1
for p, v in sorted(by_prod.items(), key=lambda x: -x[1]["churned"]/x[1]["total"]):
    pct = v["churned"] / v["total"] * 100
    print(f"  {p:25s}  {pct:5.1f}%  (n={v['total']})")

print("\nTenure cohort distribution:")
cohorts = Counter(r["tenure_cohort"] for r in rows)
for c in ["0-6m", "6-12m", "1-2yr", "2-5yr", "5yr+"]:
    print(f"  {c:8s}  {cohorts.get(c, 0)}")

print("\nChurn rate by contract type:")
by_ct = {}
for r in rows:
    by_ct.setdefault(r["contract_type"], {"total": 0, "churned": 0})
    by_ct[r["contract_type"]]["total"] += 1
    if r["status"] == "churned":
        by_ct[r["contract_type"]]["churned"] += 1
for ct, v in by_ct.items():
    print(f"  {ct:20s}  {v['churned']/v['total']*100:.1f}%")
