"""Data ingestion and validation for the customer health pipeline.

Responsibilities
----------------
* Load the raw events CSV into a typed pandas DataFrame.
* Validate the dataset (missing values, score ranges, duplicate IDs).
* Build a per-customer "latest snapshot" view used by downstream modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import pandas as pd

DEFAULT_DATA_PATH = Path("data") / "customer_health_monitoring_events.csv"

REQUIRED_COLUMNS: List[str] = [
    "event_id",
    "customer_id",
    "customer_name",
    "country",
    "industry",
    "subscription_plan",
    "account_manager",
    "event_date",
    "event_type",
    "product_name",
    "daily_active_users",
    "weekly_active_users",
    "feature_usage_score",
    "support_ticket_count",
    "avg_response_time_hours",
    "customer_health_score",
    "churn_risk_score",
    "renewal_probability_pct",
    "monthly_recurring_revenue_eur",
    "contract_value_eur",
    "alert_flag",
    "alert_type",
    "recommended_action",
]

NUMERIC_COLUMNS: List[str] = [
    "daily_active_users",
    "weekly_active_users",
    "feature_usage_score",
    "support_ticket_count",
    "avg_response_time_hours",
    "customer_health_score",
    "churn_risk_score",
    "renewal_probability_pct",
    "monthly_recurring_revenue_eur",
    "contract_value_eur",
]

# Columns whose values are expected to live in the inclusive 0..100 range.
SCORE_COLUMNS: List[str] = [
    "feature_usage_score",
    "customer_health_score",
    "churn_risk_score",
    "renewal_probability_pct",
]


@dataclass
class ValidationReport:
    """Lightweight container for the result of `validate_events`."""

    total_rows: int = 0
    unique_customers: int = 0
    missing_columns: List[str] = field(default_factory=list)
    missing_values: Dict[str, int] = field(default_factory=dict)
    out_of_range_scores: Dict[str, int] = field(default_factory=dict)
    duplicate_event_ids: int = 0
    duplicate_customer_ids: int = 0
    issues: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """A dataset is considered valid when no blocking issues were found."""
        return not self.issues

    def to_dict(self) -> Dict[str, object]:
        return {
            "total_rows": self.total_rows,
            "unique_customers": self.unique_customers,
            "missing_columns": self.missing_columns,
            "missing_values": self.missing_values,
            "out_of_range_scores": self.out_of_range_scores,
            "duplicate_event_ids": self.duplicate_event_ids,
            "duplicate_customer_ids": self.duplicate_customer_ids,
            "issues": self.issues,
            "is_valid": self.is_valid,
        }


def load_events(path: str | Path = DEFAULT_DATA_PATH) -> pd.DataFrame:
    """Load the raw events CSV into a typed DataFrame.

    Parameters
    ----------
    path:
        Path to ``customer_health_monitoring_events.csv``.
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Could not find events CSV at '{csv_path.resolve()}'. "
            "Place the file under ./data/ or pass an explicit path."
        )

    df = pd.read_csv(csv_path)

    if "event_date" in df.columns:
        df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")

    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in ("alert_type", "recommended_action"):
        if column in df.columns:
            df[column] = df[column].fillna("").astype(str)

    if "alert_flag" in df.columns:
        df["alert_flag"] = (
            df["alert_flag"].astype(str).str.upper().str.strip().eq("Y")
        )

    return df


def validate_events(df: pd.DataFrame) -> ValidationReport:
    """Run data-quality checks and return a structured report."""
    report = ValidationReport(total_rows=len(df))

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    report.missing_columns = missing_columns
    if missing_columns:
        report.issues.append(
            f"Missing required columns: {', '.join(missing_columns)}"
        )

    if "customer_id" in df.columns:
        report.unique_customers = int(df["customer_id"].nunique())

    null_counts = df.isna().sum()
    report.missing_values = {
        col: int(count) for col, count in null_counts.items() if count > 0
    }

    for column in SCORE_COLUMNS:
        if column in df.columns:
            invalid_mask = (df[column] < 0) | (df[column] > 100)
            invalid_count = int(invalid_mask.sum())
            if invalid_count:
                report.out_of_range_scores[column] = invalid_count
                report.issues.append(
                    f"{invalid_count} rows have '{column}' outside 0-100"
                )

    if "event_id" in df.columns:
        dup_event = int(df["event_id"].duplicated().sum())
        report.duplicate_event_ids = dup_event
        if dup_event:
            report.issues.append(f"{dup_event} duplicate event_id values found")

    if {"customer_id", "event_date"}.issubset(df.columns):
        dup_customer = int(
            df.duplicated(subset=["customer_id", "event_date"]).sum()
        )
        report.duplicate_customer_ids = dup_customer

    return report


def build_customer_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the event-level frame into one row per customer.

    The latest event (by ``event_date``) is treated as the authoritative
    health snapshot for each customer. Lifetime aggregates such as total
    support tickets and average response time are computed across the
    full event history.
    """
    if df.empty:
        return df.copy()

    sorted_df = df.sort_values("event_date")
    latest = sorted_df.groupby("customer_id", as_index=False).tail(1)

    aggregates = (
        df.groupby("customer_id")
        .agg(
            total_support_tickets=("support_ticket_count", "sum"),
            avg_feature_usage=("feature_usage_score", "mean"),
            avg_health_score=("customer_health_score", "mean"),
            avg_churn_risk=("churn_risk_score", "mean"),
            avg_response_time=("avg_response_time_hours", "mean"),
            event_count=("event_id", "count"),
            first_event_date=("event_date", "min"),
            last_event_date=("event_date", "max"),
        )
        .reset_index()
    )

    snapshot = latest.merge(aggregates, on="customer_id", how="left")
    snapshot = snapshot.sort_values("customer_health_score").reset_index(drop=True)
    return snapshot
