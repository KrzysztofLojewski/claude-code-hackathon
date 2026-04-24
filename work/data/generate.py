"""
Generates synthetic Sky UK subscriber data for the churn dashboard.
Covers: cohort survival, OOC exposure, MRR waterfall, churn by tenure,
propensity scores, churn reasons, and all volume breakdown dimensions.
"""

import csv
import random
import math
from datetime import date, timedelta

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

# MRR ranges per product ($/month)
PRODUCT_MRR = {
    "Netflix":             (10, 23),
    "Disney+":             (8,  14),
    "HBO Max":             (10, 16),
    "Apple TV+":           (9,  10),
    "Amazon Prime Video":  (9,  15),
    "Paramount+":          (6,  12),
    "Hulu":                (8,  18),
}

# Monthly base churn probability per product
PRODUCT_BASE_CHURN = {
    "Netflix":             0.020,
    "Disney+":             0.028,
    "HBO Max":             0.025,
    "Apple TV+":           0.035,
    "Amazon Prime Video":  0.018,
    "Paramount+":          0.042,
    "Hulu":                0.030,
}

SIM_START = date(2024, 1, 1)
SIM_END   = date(2026, 4, 1)   # ~28 months of history
N_SUBSCRIBERS = 3000


def weighted_choice(options, weights):
    r = random.random()
    cumulative = 0
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


def churn_prob_for_month(tenure_months: int, base_p: float,
                          contract_type: str, bundle_depth: str,
                          nps: int) -> float:
    p = base_p

    # Bimodal tenure effect: high in first 3m and around 12-14m renewal
    if tenure_months < 3:
        p *= 2.2
    elif 12 <= tenure_months <= 14:
        p *= 1.8
    elif tenure_months > 36:
        p *= 0.7  # loyal customers churn less

    # OOC subscribers churn more
    if contract_type == "OOC":
        p *= 1.9
    elif contract_type == "rolling-monthly":
        p *= 2.5

    # Bundle depth reduces churn (~3x less for triple play)
    if bundle_depth == "double":
        p *= 0.65
    elif bundle_depth == "triple":
        p *= 0.33

    # NPS influence
    if nps <= 3:
        p *= 1.6
    elif nps >= 9:
        p *= 0.6

    return min(p, 0.35)


rows = []

for sub_id in range(1, N_SUBSCRIBERS + 1):
    product = random.choice(PRODUCTS)
    region = weighted_choice(REGIONS, REGION_WEIGHTS)
    channel = weighted_choice(CHANNELS, CHANNEL_WEIGHTS)

    # Acquisition spread across simulation window (earlier cohorts more common)
    acq_date = random_date(SIM_START, date(2026, 1, 1))

    # Streaming-only services are almost always month-to-month
    if product in ("Netflix", "Disney+", "Apple TV+", "Paramount+", "Hulu"):
        contract_type = weighted_choice(CONTRACT_TYPES, [0.05, 0.10, 0.85])
    else:
        contract_type = weighted_choice(CONTRACT_TYPES, [0.55, 0.25, 0.20])

    contract_length_months = 0
    if contract_type == "in-contract":
        contract_length_months = random.choice([12, 18, 24])
    elif contract_type == "OOC":
        contract_length_months = random.choice([12, 24])  # already expired

    contract_end_date = None
    if contract_type == "in-contract":
        contract_end_date = acq_date + timedelta(days=contract_length_months * 30)
    elif contract_type == "OOC":
        # Rolled off between acq and now
        months_ago = random.randint(1, min(12, months_between(SIM_START, SIM_END) - 1))
        contract_end_date = SIM_END - timedelta(days=months_ago * 30)

    # Bundle depth
    bundle_depth = weighted_choice(
        ["single", "double", "triple"], [0.55, 0.30, 0.15]
    )

    mrr_lo, mrr_hi = PRODUCT_MRR[product]
    base_mrr = round(random.uniform(mrr_lo, mrr_hi), 2)
    # Bundle adds a small uplift to MRR
    if bundle_depth == "double":
        base_mrr = round(base_mrr * 1.15, 2)
    elif bundle_depth == "triple":
        base_mrr = round(base_mrr * 1.30, 2)

    nps = random.choices(range(0, 11), weights=[3,2,2,3,4,6,8,10,15,20,27])[0]

    # Simulate month-by-month to determine churn date
    base_p = PRODUCT_BASE_CHURN[product]
    churn_date = None
    plan_change = "none"

    current_month = acq_date
    tenure = 0
    while current_month < SIM_END:
        p = churn_prob_for_month(tenure, base_p, contract_type, bundle_depth, nps)
        if random.random() < p:
            # Churn happens some day in this month
            month_end = min(
                date(current_month.year, current_month.month, 28),
                SIM_END - timedelta(days=1)
            )
            churn_date = random_date(current_month, month_end)
            break

        # Occasional plan change (downgrade or upgrade)
        if plan_change == "none" and tenure > 6 and random.random() < 0.015:
            plan_change = random.choice(["upgrade", "downgrade"])
            if plan_change == "upgrade":
                base_mrr = round(base_mrr * random.uniform(1.05, 1.20), 2)
            else:
                base_mrr = round(base_mrr * random.uniform(0.75, 0.95), 2)

        current_month = date(
            current_month.year + (current_month.month // 12),
            (current_month.month % 12) + 1,
            1,
        )
        tenure += 1

    status = "churned" if churn_date else "active"

    churn_reason = None
    propensity_score = None
    if status == "churned":
        # Reason distribution varies by product
        if product in ("Disney+", "Apple TV+", "Paramount+"):
            reason_weights = [0.25, 0.20, 0.15, 0.10, 0.30]  # not_using heavy
        else:
            reason_weights = [0.35, 0.25, 0.20, 0.10, 0.10]  # price heavy
        churn_reason = weighted_choice(CHURN_REASONS, reason_weights)
        propensity_score = round(random.uniform(0.55, 0.99), 3)
    else:
        # Active subscribers get a propensity score from the model
        propensity_score = round(random.betavariate(1.5, 6), 3)

    # Tenure cohort label
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

    # Last interaction date (within last 180 days for active, before churn for churned)
    if status == "active":
        last_interaction = SIM_END - timedelta(days=random.randint(0, 180))
    else:
        last_interaction = churn_date - timedelta(days=random.randint(1, 90))

    days_to_churn = (churn_date - last_interaction).days if churn_date else None

    # Grace period flag: churned within 14 days of contract end
    grace_period = False
    if churn_date and contract_end_date:
        delta = abs((churn_date - contract_end_date).days)
        grace_period = delta <= 14

    rows.append({
        "subscriber_id":       f"SKY-{sub_id:05d}",
        "product":             product,
        "region":              region,
        "acquisition_channel": channel,
        "start_date":          acq_date.isoformat(),
        "contract_type":       contract_type,
        "contract_end_date":   contract_end_date.isoformat() if contract_end_date else "",
        "bundle_depth":        bundle_depth,
        "mrr":                 base_mrr,
        "nps_score":           nps,
        "status":              status,
        "churn_date":          churn_date.isoformat() if churn_date else "",
        "churn_reason":        churn_reason or "",
        "plan_change":         plan_change,
        "propensity_score":    propensity_score,
        "tenure_months":       tenure_months_at_end,
        "tenure_cohort":       tenure_cohort,
        "last_interaction_date": last_interaction.isoformat(),
        "days_to_churn":       days_to_churn if days_to_churn is not None else "",
        "grace_period":        str(grace_period).lower(),
    })

out_path = "/root/claude-bootcamp-setup/claude-code-hackathon/work/data/subscriptions.csv"
fieldnames = list(rows[0].keys())

with open(out_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

# Quick summary
total = len(rows)
churned = sum(1 for r in rows if r["status"] == "churned")
print(f"Rows written : {total}")
print(f"Churned      : {churned} ({churned/total*100:.1f}%)")
print(f"Active       : {total - churned}")

from collections import Counter
products = Counter(r["product"] for r in rows if r["status"] == "churned")
print("\nChurned by product:")
for p, n in products.most_common():
    print(f"  {p:25s} {n}")
