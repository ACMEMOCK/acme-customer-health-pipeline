"""CSV report exporters for the customer health pipeline.

All reports are written under :data:`REPORTS_DIR` (defaults to ``./reports``).
The directory is created on demand so the project works out-of-the-box on a
fresh checkout.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

REPORTS_DIR = Path("reports")

PORTFOLIO_SUMMARY_COLUMNS = [
    "customer_id",
    "customer_name",
    "country",
    "industry",
    "subscription_plan",
    "account_manager",
    "customer_health_score",
    "churn_risk_score",
    "feature_usage_score",
    "support_ticket_count",
    "renewal_probability_pct",
    "monthly_recurring_revenue_eur",
    "contract_value_eur",
    "composite_risk_score",
    "risk_tier",
    "revenue_at_risk_eur",
]

HIGH_RISK_EXPORT_COLUMNS = [
    "customer_id",
    "customer_name",
    "country",
    "industry",
    "subscription_plan",
    "account_manager",
    "customer_health_score",
    "composite_risk_score",
    "risk_tier",
    "renewal_probability_pct",
    "monthly_recurring_revenue_eur",
    "revenue_at_risk_eur",
    "support_ticket_count",
    "avg_response_time_hours",
]


def _ensure_reports_dir(reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def _select_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    available = [c for c in columns if c in df.columns]
    return df[available].copy()


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_summary_report(
    snapshot: pd.DataFrame,
    reports_dir: Path | str = REPORTS_DIR,
    filename: str | None = None,
) -> Path:
    """Export the per-customer portfolio summary to CSV."""
    reports_dir = _ensure_reports_dir(Path(reports_dir))
    filename = filename or f"portfolio_summary_{_timestamp()}.csv"
    output_path = reports_dir / filename

    payload = _select_columns(snapshot, PORTFOLIO_SUMMARY_COLUMNS)
    payload = payload.sort_values("composite_risk_score", ascending=False)
    payload.to_csv(output_path, index=False)
    return output_path


def export_high_risk_customers(
    snapshot: pd.DataFrame,
    reports_dir: Path | str = REPORTS_DIR,
    filename: str | None = None,
) -> Path:
    """Export only customers in the ``High Risk`` tier."""
    reports_dir = _ensure_reports_dir(Path(reports_dir))
    filename = filename or f"high_risk_customers_{_timestamp()}.csv"
    output_path = reports_dir / filename

    if "risk_tier" in snapshot.columns:
        high_risk = snapshot[snapshot["risk_tier"] == "High Risk"]
    else:
        high_risk = snapshot.iloc[0:0]

    payload = _select_columns(high_risk, HIGH_RISK_EXPORT_COLUMNS)
    payload = payload.sort_values("revenue_at_risk_eur", ascending=False)
    payload.to_csv(output_path, index=False)
    return output_path


def export_alerts_report(
    alerts: pd.DataFrame,
    reports_dir: Path | str = REPORTS_DIR,
    filename: str | None = None,
) -> Path:
    """Export the active alerts feed to CSV."""
    reports_dir = _ensure_reports_dir(Path(reports_dir))
    filename = filename or f"active_alerts_{_timestamp()}.csv"
    output_path = reports_dir / filename
    alerts.to_csv(output_path, index=False)
    return output_path


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Encode a DataFrame as CSV bytes (used by Streamlit download buttons)."""
    return df.to_csv(index=False).encode("utf-8")
