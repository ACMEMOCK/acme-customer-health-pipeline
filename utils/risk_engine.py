"""Churn risk scoring and classification.

The risk engine computes a composite churn risk score in the 0-100 range
from four signals and converts that score into a tiered label:

* **Low Risk**     - score < 35
* **Medium Risk**  - 35 <= score < 60
* **High Risk**    - score >= 60

Inputs and weights
------------------
====================  =======  ======================================
Signal                Weight   Direction
====================  =======  ======================================
churn_risk_score      0.45     Higher is worse (used as-is)
feature_usage_score   0.25     Lower is worse (inverted to 100 - x)
support_ticket_count  0.20     Higher is worse (capped at 20 tickets)
customer_health_score 0.10     Lower is worse (inverted to 100 - x)
====================  =======  ======================================
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

RISK_WEIGHTS = {
    "churn_risk_score": 0.45,
    "feature_usage_score": 0.25,
    "support_ticket_count": 0.20,
    "customer_health_score": 0.10,
}

# Tickets above this cap saturate the contribution to the composite score so a
# single noisy customer with 80 tickets does not skew the distribution.
SUPPORT_TICKET_CAP = 20

LOW_RISK_THRESHOLD = 35
HIGH_RISK_THRESHOLD = 60

RISK_TIER_ORDER = ["Low Risk", "Medium Risk", "High Risk"]


def _normalise_tickets(tickets: pd.Series) -> pd.Series:
    """Scale support ticket counts onto a 0-100 axis with a soft cap."""
    capped = tickets.clip(lower=0, upper=SUPPORT_TICKET_CAP)
    return (capped / SUPPORT_TICKET_CAP) * 100


def compute_composite_score(df: pd.DataFrame) -> pd.Series:
    """Return the weighted churn risk score for each row of ``df``."""
    churn = df["churn_risk_score"].fillna(0)
    inverse_usage = 100 - df["feature_usage_score"].fillna(0)
    inverse_health = 100 - df["customer_health_score"].fillna(0)
    tickets = _normalise_tickets(df["support_ticket_count"].fillna(0))

    composite = (
        churn * RISK_WEIGHTS["churn_risk_score"]
        + inverse_usage * RISK_WEIGHTS["feature_usage_score"]
        + tickets * RISK_WEIGHTS["support_ticket_count"]
        + inverse_health * RISK_WEIGHTS["customer_health_score"]
    )
    return composite.clip(lower=0, upper=100).round(2)


def classify_risk(score: float) -> str:
    """Map a numeric composite score to a tier label."""
    if pd.isna(score):
        return "Unknown"
    if score < LOW_RISK_THRESHOLD:
        return "Low Risk"
    if score < HIGH_RISK_THRESHOLD:
        return "Medium Risk"
    return "High Risk"


def enrich_with_risk(df: pd.DataFrame) -> pd.DataFrame:
    """Attach ``composite_risk_score`` and ``risk_tier`` columns to ``df``."""
    if df.empty:
        enriched = df.copy()
        enriched["composite_risk_score"] = pd.Series(dtype=float)
        enriched["risk_tier"] = pd.Series(dtype=str)
        enriched["revenue_at_risk_eur"] = pd.Series(dtype=float)
        return enriched

    enriched = df.copy()
    enriched["composite_risk_score"] = compute_composite_score(enriched)
    enriched["risk_tier"] = enriched["composite_risk_score"].apply(classify_risk)
    enriched["risk_tier"] = pd.Categorical(
        enriched["risk_tier"], categories=RISK_TIER_ORDER + ["Unknown"], ordered=True
    )

    # Revenue at risk = MRR * (composite_risk_score / 100). It approximates the
    # expected monthly revenue exposure from a customer churning.
    enriched["revenue_at_risk_eur"] = (
        enriched["monthly_recurring_revenue_eur"].fillna(0)
        * (enriched["composite_risk_score"] / 100)
    ).round(2)

    return enriched


def risk_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Return counts and revenue exposure grouped by risk tier."""
    if df.empty or "risk_tier" not in df.columns:
        return pd.DataFrame(
            columns=["risk_tier", "customers", "revenue_at_risk_eur"]
        )

    grouped = (
        df.groupby("risk_tier", observed=True)
        .agg(
            customers=("customer_id", "nunique"),
            revenue_at_risk_eur=("revenue_at_risk_eur", "sum"),
        )
        .reset_index()
    )
    grouped["revenue_at_risk_eur"] = grouped["revenue_at_risk_eur"].round(2)
    return grouped


def summarise_portfolio(df: pd.DataFrame) -> Tuple[int, float, int, float]:
    """Return the four headline metrics shown on the dashboard.

    Returns
    -------
    (total_customers, avg_health_score, high_risk_customers, revenue_at_risk_eur)
    """
    if df.empty:
        return 0, 0.0, 0, 0.0

    total_customers = int(df["customer_id"].nunique())
    avg_health = float(np.nanmean(df["customer_health_score"]))
    high_risk = int((df["risk_tier"] == "High Risk").sum())
    revenue_at_risk = float(df["revenue_at_risk_eur"].sum())
    return total_customers, round(avg_health, 1), high_risk, round(revenue_at_risk, 2)
