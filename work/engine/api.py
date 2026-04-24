"""
Sky UK Churn Dashboard API
Serves pre-computed metrics from data/subscriptions.csv.
Every response carries definition_version so callers know which churn
definition produced the numbers.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFINITION_VERSION = "churn_v1"
DATA_PATH = Path(__file__).parent.parent / "data" / "subscriptions.csv"
SIM_END = date(2026, 4, 1)

app = FastAPI(
    title="Sky UK Churn Dashboard API",
    description="Metrics derived from synthetic subscriber data. "
                "Every response is tagged with definition_version.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_df() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["start_date", "churn_date",
                                              "contract_end_date",
                                              "last_interaction_date"])
    df["churn_month"] = df["churn_date"].dt.to_period("M")
    df["start_month"] = df["start_date"].dt.to_period("M")
    return df


def meta(extra: dict | None = None) -> dict:
    base = {"definition_version": DEFINITION_VERSION, "generated_at": SIM_END.isoformat()}
    return {**base, **(extra or {})}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def active_at(df: pd.DataFrame, snapshot: date) -> pd.DataFrame:
    """Subscribers who were active on a given date."""
    snap = pd.Timestamp(snapshot)
    started = df["start_date"] <= snap
    not_churned = df["churn_date"].isna() | (df["churn_date"] > snap)
    return df[started & not_churned]


def period_df(df: pd.DataFrame, year: int, month: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (active-at-start, churned-in-period) for a calendar month."""
    period_start = date(year, month, 1)
    next_month = month % 12 + 1
    next_year = year + (1 if month == 12 else 0)
    period_end = date(next_year, next_month, 1)

    active_start = active_at(df, period_start)

    churned = df[
        (df["churn_date"] >= pd.Timestamp(period_start)) &
        (df["churn_date"] < pd.Timestamp(period_end))
    ]
    return active_start, churned


# ---------------------------------------------------------------------------
# Routes — Volume & Base KPIs
# ---------------------------------------------------------------------------

@app.get("/kpis/summary")
def kpis_summary(
    year: int = Query(default=2026),
    month: int = Query(default=3, ge=1, le=12),
):
    """Top-level KPIs for a given month."""
    df = load_df()
    period_start = date(year, month, 1)
    next_m = month % 12 + 1
    next_y = year + (1 if month == 12 else 0)
    period_end = date(next_y, next_m, 1)

    active_start = active_at(df, period_start)
    active_end   = active_at(df, period_end - pd.Timedelta(days=1))

    gross_adds = df[
        (df["start_date"] >= pd.Timestamp(period_start)) &
        (df["start_date"] < pd.Timestamp(period_end))
    ]
    churned = df[
        (df["churn_date"] >= pd.Timestamp(period_start)) &
        (df["churn_date"] < pd.Timestamp(period_end))
    ]

    active_count = len(active_start)
    gross_adds_count = len(gross_adds)
    gross_churn_count = len(churned)
    net_adds = gross_adds_count - gross_churn_count

    churn_rate = round(gross_churn_count / active_count * 100, 2) if active_count else 0

    mrr_start = round(active_start["mrr"].sum(), 2)
    mrr_churned = round(churned["mrr"].sum(), 2)
    mrr_churn_pct = round(mrr_churned / mrr_start * 100, 2) if mrr_start else 0

    return {
        **meta({"period": f"{year}-{month:02d}"}),
        "total_active_subscribers": active_count,
        "gross_adds": gross_adds_count,
        "gross_churn": gross_churn_count,
        "net_adds": net_adds,
        "churn_rate_pct": churn_rate,
        "mrr": mrr_start,
        "mrr_churned": mrr_churned,
        "mrr_churn_pct": mrr_churn_pct,
    }


# ---------------------------------------------------------------------------
# Routes — Churn Rate Trend (rolling 13 months)
# ---------------------------------------------------------------------------

@app.get("/charts/churn-rate-trend")
def churn_rate_trend(
    end_year: int = Query(default=2026),
    end_month: int = Query(default=3, ge=1, le=12),
    months: int = Query(default=13, ge=1, le=36),
    product: Optional[str] = Query(default=None),
):
    """Monthly churn rate % for up to 36 months, optionally filtered by product."""
    df = load_df()
    if product:
        df = df[df["product"] == product]
        if df.empty:
            raise HTTPException(404, f"Product '{product}' not found")

    result = []
    yr, mo = end_year, end_month
    for _ in range(months):
        active_start, churned = period_df(df, yr, mo)
        n = len(active_start)
        rate = round(len(churned) / n * 100, 2) if n else 0
        result.append({"period": f"{yr}-{mo:02d}", "churn_rate_pct": rate,
                        "churned": len(churned), "active_at_start": n})
        mo -= 1
        if mo == 0:
            mo = 12
            yr -= 1

    result.reverse()
    return {**meta(), "product_filter": product, "series": result}


# ---------------------------------------------------------------------------
# Routes — Cohort Survival
# ---------------------------------------------------------------------------

@app.get("/charts/cohort-survival")
def cohort_survival(
    max_months: int = Query(default=24, ge=1, le=36),
):
    """
    Cohort survival table.
    Returns % of each start-month cohort still active at M0..M{max_months}.
    """
    df = load_df()
    cohorts = sorted(df["start_month"].dropna().unique())

    rows = []
    for cohort in cohorts:
        cohort_subs = df[df["start_month"] == cohort]
        n = len(cohort_subs)
        if n == 0:
            continue
        cohort_start = cohort.to_timestamp().date()
        survival = []
        for m in range(max_months + 1):
            snap = date(
                cohort_start.year + (cohort_start.month - 1 + m) // 12,
                (cohort_start.month - 1 + m) % 12 + 1,
                1,
            )
            if snap > SIM_END:
                break
            still_active = active_at(cohort_subs, snap)
            survival.append({
                "month_offset": m,
                "retention_pct": round(len(still_active) / n * 100, 1),
                "active_count": len(still_active),
            })
        rows.append({
            "cohort": str(cohort),
            "cohort_size": n,
            "survival": survival,
        })

    return {**meta(), "cohorts": rows}


# ---------------------------------------------------------------------------
# Routes — OOC Exposure
# ---------------------------------------------------------------------------

@app.get("/charts/ooc-exposure")
def ooc_exposure(
    months_ahead: int = Query(default=12, ge=1, le=24),
):
    """Volume of subscribers coming off contract each month for the next N months."""
    df = load_df()
    df_ooc = df[df["contract_end_date"].notna() & (df["status"] == "active")].copy()

    result = []
    for i in range(months_ahead):
        mo_start = date(
            SIM_END.year + (SIM_END.month - 1 + i) // 12,
            (SIM_END.month - 1 + i) % 12 + 1,
            1,
        )
        mo_end = date(
            SIM_END.year + (SIM_END.month + i) // 12,
            (SIM_END.month + i) % 12 + 1,
            1,
        )
        expiring = df_ooc[
            (df_ooc["contract_end_date"] >= pd.Timestamp(mo_start)) &
            (df_ooc["contract_end_date"] < pd.Timestamp(mo_end))
        ]
        by_product = expiring.groupby("product").size().to_dict()
        result.append({
            "period": f"{mo_start.year}-{mo_start.month:02d}",
            "total_expiring": len(expiring),
            "by_product": by_product,
            "at_risk_mrr": round(expiring["mrr"].sum(), 2),
        })

    return {**meta(), "series": result}


# ---------------------------------------------------------------------------
# Routes — Churn by Tenure
# ---------------------------------------------------------------------------

@app.get("/charts/churn-by-tenure")
def churn_by_tenure():
    """Histogram of churn events bucketed by tenure month (0-36+)."""
    df = load_df()
    churned = df[df["status"] == "churned"].copy()

    buckets: dict[str, int] = {}
    for _, row in churned.iterrows():
        m = int(row["tenure_months"])
        label = f"{m}m" if m <= 36 else "36m+"
        buckets[label] = buckets.get(label, 0) + 1

    sorted_buckets = [
        {"tenure": k, "churn_count": v}
        for k, v in sorted(
            buckets.items(),
            key=lambda x: int(x[0].rstrip("m+")) if x[0] != "36m+" else 37
        )
    ]
    return {**meta(), "histogram": sorted_buckets}


# ---------------------------------------------------------------------------
# Routes — MRR Waterfall
# ---------------------------------------------------------------------------

@app.get("/charts/mrr-waterfall")
def mrr_waterfall(
    year: int = Query(default=2026),
    month: int = Query(default=3, ge=1, le=12),
):
    """MRR bridge for a given month: start → +adds → -churn → ±plan changes → end."""
    df = load_df()
    period_start = date(year, month, 1)
    next_m = month % 12 + 1
    next_y = year + (1 if month == 12 else 0)
    period_end = date(next_y, next_m, 1)

    active_start = active_at(df, period_start)
    mrr_start = round(active_start["mrr"].sum(), 2)

    adds = df[
        (df["start_date"] >= pd.Timestamp(period_start)) &
        (df["start_date"] < pd.Timestamp(period_end))
    ]
    churned = df[
        (df["churn_date"] >= pd.Timestamp(period_start)) &
        (df["churn_date"] < pd.Timestamp(period_end))
    ]

    # Plan-change MRR delta for active subs that changed this month
    # (approximated: subscribers with plan_change != none acquired before period_start)
    upgrades = active_start[active_start["plan_change"] == "upgrade"]
    downgrades = active_start[active_start["plan_change"] == "downgrade"]
    upgrade_mrr   = round(upgrades["mrr"].sum() * 0.12, 2)   # ~12% uplift portion
    downgrade_mrr = round(downgrades["mrr"].sum() * 0.15, 2) # ~15% reduction portion

    mrr_adds    = round(adds["mrr"].sum(), 2)
    mrr_churned = round(churned["mrr"].sum(), 2)
    mrr_end = round(mrr_start + mrr_adds - mrr_churned + upgrade_mrr - downgrade_mrr, 2)

    return {
        **meta({"period": f"{year}-{month:02d}"}),
        "mrr_start":     mrr_start,
        "mrr_gross_adds": mrr_adds,
        "mrr_churned":   -mrr_churned,
        "mrr_upgrades":  upgrade_mrr,
        "mrr_downgrades": -downgrade_mrr,
        "mrr_end":       mrr_end,
    }


# ---------------------------------------------------------------------------
# Routes — Churn Reason Pareto
# ---------------------------------------------------------------------------

@app.get("/charts/churn-reasons")
def churn_reasons(product: Optional[str] = Query(default=None)):
    """Churn reason breakdown as % of total churn volume."""
    df = load_df()
    churned = df[df["status"] == "churned"]
    if product:
        churned = churned[churned["product"] == product]
        if churned.empty:
            raise HTTPException(404, f"Product '{product}' not found or has no churn")

    total = len(churned)
    counts = churned["churn_reason"].value_counts()
    reasons = [
        {"reason": r, "count": int(n), "pct": round(n / total * 100, 1)}
        for r, n in counts.items()
    ]
    return {**meta(), "product_filter": product, "total_churned": total, "reasons": reasons}


# ---------------------------------------------------------------------------
# Routes — Propensity Score Distribution
# ---------------------------------------------------------------------------

@app.get("/charts/propensity-distribution")
def propensity_distribution(bins: int = Query(default=10, ge=5, le=20)):
    """Histogram of churn propensity scores for active subscribers."""
    df = load_df()
    active = df[df["status"] == "active"].copy()

    bin_size = 1.0 / bins
    result = []
    for i in range(bins):
        lo = round(i * bin_size, 3)
        hi = round((i + 1) * bin_size, 3)
        bucket = active[(active["propensity_score"] >= lo) & (active["propensity_score"] < hi)]
        result.append({
            "score_band": f"{lo:.2f}-{hi:.2f}",
            "subscriber_count": len(bucket),
            "mrr_at_risk": round(bucket["mrr"].sum(), 2),
            "high_risk": hi > 0.7,
        })

    return {**meta(), "bins": result}


# ---------------------------------------------------------------------------
# Routes — At-Risk Funnel
# ---------------------------------------------------------------------------

@app.get("/charts/at-risk-funnel")
def at_risk_funnel():
    """
    Simplified save funnel for OOC subscribers.
    Propensity > 0.7 → contacted (80%) → engaged (55%) → saved (40%) → churned rest.
    Ratios are model-estimated; replace with CRM data in production.
    """
    df = load_df()
    ooc = df[(df["contract_type"] == "OOC") & (df["status"] == "active")]

    total_ooc = len(ooc)
    contacted   = math.floor(total_ooc * 0.80)
    engaged     = math.floor(contacted  * 0.55)
    saved       = math.floor(engaged    * 0.40)
    churned_est = total_ooc - saved

    return {
        **meta(),
        "total_ooc_subscribers": total_ooc,
        "contacted":  contacted,
        "engaged":    engaged,
        "saved":      saved,
        "churned_estimate": churned_est,
        "save_rate_pct": round(saved / contacted * 100, 1) if contacted else 0,
        "note": "contacted/engaged/saved ratios are model-estimated",
    }


# ---------------------------------------------------------------------------
# Routes — By-Dimension Breakdown
# ---------------------------------------------------------------------------

@app.get("/breakdown/{dimension}")
def breakdown(
    dimension: str,
    year: int = Query(default=2026),
    month: int = Query(default=3, ge=1, le=12),
):
    """
    Churn rate broken down by a single dimension.
    dimension: product | region | acquisition_channel | contract_type |
               bundle_depth | tenure_cohort
    """
    allowed = {"product", "region", "acquisition_channel",
               "contract_type", "bundle_depth", "tenure_cohort"}
    if dimension not in allowed:
        raise HTTPException(400, f"dimension must be one of {sorted(allowed)}")

    df = load_df()
    active_start, churned = period_df(df, year, month)

    active_counts = active_start.groupby(dimension).size()
    churn_counts  = churned.groupby(dimension).size()
    mrr_lost      = churned.groupby(dimension)["mrr"].sum()

    rows = []
    for val in active_counts.index:
        a = int(active_counts.get(val, 0))
        c = int(churn_counts.get(val, 0))
        rows.append({
            dimension: val,
            "active_at_start": a,
            "churned": c,
            "churn_rate_pct": round(c / a * 100, 2) if a else 0,
            "mrr_lost": round(float(mrr_lost.get(val, 0)), 2),
        })

    rows.sort(key=lambda r: r["churn_rate_pct"], reverse=True)
    return {**meta({"period": f"{year}-{month:02d}", "dimension": dimension}), "rows": rows}


# ---------------------------------------------------------------------------
# Routes — Renewal Forecast
# ---------------------------------------------------------------------------

@app.get("/forecast/renewal")
def renewal_forecast(horizon_days: int = Query(default=90, ge=1, le=365)):
    """
    Contracts expiring within horizon_days, with predicted churn and at-risk MRR.
    Predicted churn rate = mean propensity score of expiring subs.
    """
    df = load_df()
    today = pd.Timestamp(SIM_END)
    horizon = today + pd.Timedelta(days=horizon_days)

    expiring = df[
        df["contract_end_date"].notna() &
        (df["contract_end_date"] >= today) &
        (df["contract_end_date"] <= horizon) &
        (df["status"] == "active")
    ]

    n = len(expiring)
    if n == 0:
        return {**meta(), "expiring_count": 0, "horizon_days": horizon_days}

    predicted_churn_rate = round(float(expiring["propensity_score"].mean()), 3)
    at_risk_mrr = round(float(expiring["mrr"].sum()) * predicted_churn_rate, 2)

    by_product = (
        expiring.groupby("product")
        .agg(count=("subscriber_id", "size"), mrr=("mrr", "sum"),
             avg_propensity=("propensity_score", "mean"))
        .reset_index()
        .rename(columns={"product": "product"})
        .assign(mrr=lambda d: d["mrr"].round(2),
                avg_propensity=lambda d: d["avg_propensity"].round(3))
        .to_dict(orient="records")
    )

    return {
        **meta(),
        "horizon_days": horizon_days,
        "expiring_contracts": n,
        "total_expiring_mrr": round(float(expiring["mrr"].sum()), 2),
        "predicted_churn_rate": predicted_churn_rate,
        "at_risk_mrr": at_risk_mrr,
        "by_product": by_product,
    }


# ---------------------------------------------------------------------------
# Routes — Raw subscriber list (paginated)
# ---------------------------------------------------------------------------

@app.get("/subscribers")
def subscribers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    product: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None),
):
    """Paginated subscriber list with optional filters."""
    df = load_df()
    if product:
        df = df[df["product"] == product]
    if status:
        df = df[df["status"] == status]
    if region:
        df = df[df["region"] == region]

    total = len(df)
    start = (page - 1) * page_size
    page_df = df.iloc[start: start + page_size].copy()

    # Coerce NaT/NaN to None for JSON serialisation
    page_df = page_df.where(pd.notnull(page_df), None)
    for col in ["start_date", "churn_date", "contract_end_date", "last_interaction_date"]:
        page_df[col] = page_df[col].apply(
            lambda v: v.date().isoformat() if pd.notna(v) and v is not None else None
        )

    return {
        **meta(),
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": page_df.to_dict(orient="records"),
    }
