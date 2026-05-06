"""Rule-based alert generation for the customer health pipeline.

Alerts are produced from the risk-enriched per-customer snapshot. A single
customer can trigger more than one alert. Each alert row carries a
``severity`` (Critical / High / Medium) and a ``recommended_action``
which the dashboard surfaces directly to the account team.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

import pandas as pd

# ---- Alert thresholds (tuneable in one place) -------------------------------

HIGH_CHURN_RISK_SCORE = 60        # composite score >=
LOW_FEATURE_USAGE_SCORE = 40      # feature_usage_score <=
SLA_RESPONSE_TIME_HOURS = 24      # avg_response_time_hours >
SLA_TICKET_THRESHOLD = 8          # support_ticket_count >=
REVENUE_RISK_MRR_EUR = 10_000     # monthly_recurring_revenue_eur >=
REVENUE_RISK_RENEWAL_PCT = 60     # renewal_probability_pct <


@dataclass(frozen=True)
class AlertRule:
    """Declarative description of a single alert rule."""

    alert_type: str
    severity: str
    description: str
    recommended_action: str
    predicate: Callable[[pd.DataFrame], pd.Series]


def _high_churn_risk(df: pd.DataFrame) -> pd.Series:
    return df["composite_risk_score"] >= HIGH_CHURN_RISK_SCORE


def _low_adoption(df: pd.DataFrame) -> pd.Series:
    return df["feature_usage_score"] <= LOW_FEATURE_USAGE_SCORE


def _sla_breach(df: pd.DataFrame) -> pd.Series:
    response_breach = df["avg_response_time_hours"] > SLA_RESPONSE_TIME_HOURS
    ticket_breach = df["support_ticket_count"] >= SLA_TICKET_THRESHOLD
    return response_breach | ticket_breach


def _revenue_risk(df: pd.DataFrame) -> pd.Series:
    return (
        (df["monthly_recurring_revenue_eur"] >= REVENUE_RISK_MRR_EUR)
        & (df["renewal_probability_pct"] < REVENUE_RISK_RENEWAL_PCT)
    )


ALERT_RULES: List[AlertRule] = [
    AlertRule(
        alert_type="High Churn Risk",
        severity="Critical",
        description="Composite churn risk score is in the high-risk band.",
        recommended_action="Schedule executive save-call and renewal review",
        predicate=_high_churn_risk,
    ),
    AlertRule(
        alert_type="Low Product Adoption",
        severity="High",
        description="Feature usage score indicates poor product adoption.",
        recommended_action="Run targeted enablement / training session",
        predicate=_low_adoption,
    ),
    AlertRule(
        alert_type="SLA Breach",
        severity="High",
        description="Support response time or ticket volume exceeds SLA.",
        recommended_action="Escalate to support manager and root-cause review",
        predicate=_sla_breach,
    ),
    AlertRule(
        alert_type="Revenue at Risk",
        severity="Critical",
        description="High-value account with low renewal probability.",
        recommended_action="Account manager + CSM joint renewal plan",
        predicate=_revenue_risk,
    ),
]

ALERT_COLUMNS = [
    "customer_id",
    "customer_name",
    "country",
    "industry",
    "subscription_plan",
    "account_manager",
    "monthly_recurring_revenue_eur",
    "renewal_probability_pct",
    "composite_risk_score",
    "risk_tier",
    "alert_type",
    "severity",
    "description",
    "recommended_action",
]


def generate_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """Apply each rule in :data:`ALERT_RULES` and return the long-form alerts.

    Parameters
    ----------
    df:
        The risk-enriched per-customer snapshot produced by
        :func:`utils.risk_engine.enrich_with_risk`.
    """
    if df.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    alert_frames: List[pd.DataFrame] = []
    for rule in ALERT_RULES:
        mask = rule.predicate(df).fillna(False)
        if not mask.any():
            continue
        subset = df.loc[mask].copy()
        subset["alert_type"] = rule.alert_type
        subset["severity"] = rule.severity
        subset["description"] = rule.description
        subset["recommended_action"] = rule.recommended_action
        alert_frames.append(subset)

    if not alert_frames:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    alerts = pd.concat(alert_frames, ignore_index=True)
    available_columns = [c for c in ALERT_COLUMNS if c in alerts.columns]
    alerts = alerts[available_columns]

    severity_order = {"Critical": 0, "High": 1, "Medium": 2}
    alerts["_severity_rank"] = alerts["severity"].map(severity_order).fillna(99)
    alerts = (
        alerts.sort_values(
            ["_severity_rank", "composite_risk_score"],
            ascending=[True, False],
        )
        .drop(columns=["_severity_rank"])
        .reset_index(drop=True)
    )
    return alerts


def alerts_summary(alerts: pd.DataFrame) -> pd.DataFrame:
    """Return alert counts grouped by ``alert_type`` and ``severity``."""
    if alerts.empty:
        return pd.DataFrame(columns=["alert_type", "severity", "count"])

    summary = (
        alerts.groupby(["alert_type", "severity"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )
    return summary
