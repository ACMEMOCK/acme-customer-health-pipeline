"""Acme Customer Health Pipeline - Streamlit Dashboard.

Run locally with::

    streamlit run app.py

The app loads ``data/customer_health_monitoring_events.csv``, validates it,
computes a composite churn risk score per customer, generates rule-based
alerts and renders an interactive operational dashboard for SaaS customer
success teams.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.alert_generator import alerts_summary, generate_alerts
from utils.data_loader import (
    DEFAULT_DATA_PATH,
    build_customer_snapshot,
    load_events,
    validate_events,
)
from utils.reporting import (
    HIGH_RISK_EXPORT_COLUMNS,
    PORTFOLIO_SUMMARY_COLUMNS,
    dataframe_to_csv_bytes,
    export_alerts_report,
    export_high_risk_customers,
    export_summary_report,
)
from utils.risk_engine import (
    RISK_TIER_ORDER,
    enrich_with_risk,
    risk_distribution,
    summarise_portfolio,
)

# ---- Page setup -------------------------------------------------------------

st.set_page_config(
    page_title="Acme Customer Health Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY_COLOR = "#2E5BFF"
RISK_COLORS = {
    "Low Risk": "#1F9D55",
    "Medium Risk": "#F2A93B",
    "High Risk": "#E63946",
    "Unknown": "#9CA3AF",
}

CUSTOM_CSS = """
<style>
.main > div { padding-top: 1rem; }
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
[data-testid="stMetricLabel"] p {
    font-size: 0.85rem;
    color: #6B7280;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stMetricValue"] {
    color: #0F172A;
    font-weight: 600;
}
section[data-testid="stSidebar"] { background: #F8FAFC; }
h1, h2, h3 { color: #0F172A; }
.dataframe tbody tr th { display: none; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---- Data layer (cached) ----------------------------------------------------

@st.cache_data(show_spinner=False)
def load_pipeline(path: str) -> dict:
    """Load events, run validation and build the enriched snapshot.

    Returns a dictionary with: ``events``, ``snapshot``, ``alerts`` and
    ``validation`` so the UI can render everything from one cached payload.
    """
    events = load_events(path)
    validation = validate_events(events)
    snapshot = build_customer_snapshot(events)
    snapshot = enrich_with_risk(snapshot)
    alerts = generate_alerts(snapshot)
    return {
        "events": events,
        "snapshot": snapshot,
        "alerts": alerts,
        "validation": validation,
    }


def _format_currency(value: float) -> str:
    return f"€{value:,.0f}"


# ---- Sidebar ----------------------------------------------------------------

def render_sidebar(snapshot: pd.DataFrame) -> dict:
    st.sidebar.title("🔎 Filters")
    st.sidebar.caption("Refine the cohort feeding every chart and table.")

    countries = sorted(snapshot["country"].dropna().unique().tolist())
    industries = sorted(snapshot["industry"].dropna().unique().tolist())
    plans = sorted(snapshot["subscription_plan"].dropna().unique().tolist())
    managers = sorted(snapshot["account_manager"].dropna().unique().tolist())

    selected_countries = st.sidebar.multiselect(
        "Country", countries, default=countries
    )
    selected_industries = st.sidebar.multiselect(
        "Industry", industries, default=industries
    )
    selected_plans = st.sidebar.multiselect(
        "Subscription plan", plans, default=plans
    )
    selected_managers = st.sidebar.multiselect(
        "Account manager", managers, default=managers
    )
    selected_tiers = st.sidebar.multiselect(
        "Risk tier", RISK_TIER_ORDER, default=RISK_TIER_ORDER
    )

    health_min, health_max = st.sidebar.slider(
        "Health score range", min_value=0, max_value=100, value=(0, 100)
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "Built with ❤️ using **Streamlit**, **pandas** and **Plotly**."
    )

    return {
        "countries": selected_countries,
        "industries": selected_industries,
        "plans": selected_plans,
        "managers": selected_managers,
        "tiers": selected_tiers,
        "health_range": (health_min, health_max),
    }


def apply_filters(snapshot: pd.DataFrame, filters: dict) -> pd.DataFrame:
    df = snapshot.copy()
    if filters["countries"]:
        df = df[df["country"].isin(filters["countries"])]
    if filters["industries"]:
        df = df[df["industry"].isin(filters["industries"])]
    if filters["plans"]:
        df = df[df["subscription_plan"].isin(filters["plans"])]
    if filters["managers"]:
        df = df[df["account_manager"].isin(filters["managers"])]
    if filters["tiers"]:
        df = df[df["risk_tier"].astype(str).isin(filters["tiers"])]

    low, high = filters["health_range"]
    df = df[(df["customer_health_score"] >= low) & (df["customer_health_score"] <= high)]
    return df.reset_index(drop=True)


# ---- UI sections ------------------------------------------------------------

def render_header(validation) -> None:
    st.title("📊 Acme Customer Health Pipeline")
    st.caption(
        "Operational dashboard for SaaS customer success teams - "
        "monitor health, churn risk, SLA breaches and revenue exposure."
    )

    if validation.issues:
        st.warning(
            "Data quality issues detected: " + " · ".join(validation.issues)
        )
    else:
        st.success(
            f"✅ Data validated · {validation.total_rows} events · "
            f"{validation.unique_customers} customers"
        )


def render_top_metrics(snapshot: pd.DataFrame) -> None:
    total_customers, avg_health, high_risk, revenue_at_risk = summarise_portfolio(
        snapshot
    )

    cols = st.columns(4)
    cols[0].metric("Total Customers", f"{total_customers:,}")
    cols[1].metric("Avg Health Score", f"{avg_health:.1f} / 100")
    cols[2].metric(
        "High Risk Customers",
        f"{high_risk:,}",
        delta=f"{(high_risk / total_customers * 100):.0f}% of book"
        if total_customers
        else None,
        delta_color="inverse",
    )
    cols[3].metric("Revenue at Risk", _format_currency(revenue_at_risk))


def render_charts(events: pd.DataFrame, snapshot: pd.DataFrame) -> None:
    st.subheader("Portfolio analytics")

    row1_left, row1_right = st.columns(2)

    with row1_left:
        fig = px.histogram(
            snapshot,
            x="customer_health_score",
            nbins=15,
            color="risk_tier",
            color_discrete_map=RISK_COLORS,
            category_orders={"risk_tier": RISK_TIER_ORDER},
            title="Health Score Distribution",
        )
        fig.update_layout(
            bargap=0.05,
            xaxis_title="Customer health score",
            yaxis_title="Customers",
            legend_title="Risk tier",
        )
        st.plotly_chart(fig, use_container_width=True)

    with row1_right:
        country_risk = (
            snapshot.groupby("country", observed=True)
            .agg(
                avg_churn_risk=("composite_risk_score", "mean"),
                customers=("customer_id", "nunique"),
            )
            .reset_index()
            .sort_values("avg_churn_risk", ascending=False)
        )
        fig = px.bar(
            country_risk,
            x="avg_churn_risk",
            y="country",
            orientation="h",
            color="avg_churn_risk",
            color_continuous_scale="RdYlGn_r",
            title="Avg Churn Risk by Country",
            hover_data={"customers": True, "avg_churn_risk": ":.1f"},
        )
        fig.update_layout(
            xaxis_title="Composite churn risk",
            yaxis_title=None,
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    row2_left, row2_right = st.columns(2)

    with row2_left:
        usage_trend = (
            events.assign(month=events["event_date"].dt.to_period("M").dt.to_timestamp())
            .groupby(["month", "product_name"], as_index=False)["feature_usage_score"]
            .mean()
        )
        fig = px.line(
            usage_trend,
            x="month",
            y="feature_usage_score",
            color="product_name",
            markers=True,
            title="Feature Usage Trends",
        )
        fig.update_layout(
            xaxis_title="Month",
            yaxis_title="Avg feature usage score",
            legend_title="Product",
        )
        st.plotly_chart(fig, use_container_width=True)

    with row2_right:
        plan_revenue = (
            snapshot.groupby("subscription_plan", as_index=False)
            .agg(
                revenue_at_risk_eur=("revenue_at_risk_eur", "sum"),
                customers=("customer_id", "nunique"),
            )
            .sort_values("revenue_at_risk_eur", ascending=False)
        )
        fig = px.bar(
            plan_revenue,
            x="subscription_plan",
            y="revenue_at_risk_eur",
            color="subscription_plan",
            text_auto=".2s",
            title="Revenue at Risk by Plan",
        )
        fig.update_layout(
            xaxis_title="Subscription plan",
            yaxis_title="Revenue at risk (EUR)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    fig = px.scatter(
        snapshot,
        x="support_ticket_count",
        y="customer_health_score",
        color="risk_tier",
        size="monthly_recurring_revenue_eur",
        hover_name="customer_name",
        hover_data={
            "country": True,
            "subscription_plan": True,
            "composite_risk_score": ":.1f",
            "monthly_recurring_revenue_eur": ":,.0f",
        },
        color_discrete_map=RISK_COLORS,
        category_orders={"risk_tier": RISK_TIER_ORDER},
        title="Support Tickets vs Health Score",
    )
    fig.update_layout(
        xaxis_title="Support tickets",
        yaxis_title="Customer health score",
        legend_title="Risk tier",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_tables(snapshot: pd.DataFrame, alerts: pd.DataFrame) -> None:
    st.subheader("Action centre")

    tab1, tab2, tab3 = st.tabs(
        ["🔥 Top Risk Customers", "🚨 Active Alerts", "🧭 Recommended Actions"]
    )

    with tab1:
        top_risk = (
            snapshot.sort_values("composite_risk_score", ascending=False)
            .head(15)
        )
        display_cols = [c for c in HIGH_RISK_EXPORT_COLUMNS if c in top_risk.columns]
        st.dataframe(
            top_risk[display_cols].style.format(
                {
                    "monthly_recurring_revenue_eur": "€{:,.0f}",
                    "revenue_at_risk_eur": "€{:,.0f}",
                    "composite_risk_score": "{:.1f}",
                    "customer_health_score": "{:.0f}",
                    "renewal_probability_pct": "{:.0f}%",
                    "avg_response_time_hours": "{:.1f}h",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with tab2:
        if alerts.empty:
            st.info("No active alerts in the current cohort. ✨")
        else:
            summary = alerts_summary(alerts)
            cols = st.columns(len(summary)) if not summary.empty else [st]
            for col, (_, row) in zip(cols, summary.iterrows()):
                col.metric(
                    f"{row['alert_type']}",
                    f"{row['count']:,}",
                    delta=row["severity"],
                    delta_color="off",
                )

            st.dataframe(
                alerts.style.format(
                    {
                        "monthly_recurring_revenue_eur": "€{:,.0f}",
                        "renewal_probability_pct": "{:.0f}%",
                        "composite_risk_score": "{:.1f}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    with tab3:
        if alerts.empty:
            st.info("No recommended actions - portfolio is healthy.")
        else:
            actions = (
                alerts.groupby(
                    ["customer_id", "customer_name", "account_manager"],
                    as_index=False,
                )
                .agg(
                    risk_tier=("risk_tier", "first"),
                    alerts=("alert_type", lambda s: ", ".join(sorted(set(s)))),
                    actions=(
                        "recommended_action",
                        lambda s: " • ".join(sorted(set(s))),
                    ),
                    revenue_at_risk_eur=("monthly_recurring_revenue_eur", "first"),
                )
                .sort_values("revenue_at_risk_eur", ascending=False)
            )
            st.dataframe(
                actions.style.format({"revenue_at_risk_eur": "€{:,.0f}"}),
                use_container_width=True,
                hide_index=True,
            )


def render_exports(snapshot: pd.DataFrame, alerts: pd.DataFrame) -> None:
    st.subheader("Reports & exports")
    st.caption(
        "Download CSVs directly or persist them under `./reports/` for the "
        "wider analytics team."
    )

    summary_cols = [c for c in PORTFOLIO_SUMMARY_COLUMNS if c in snapshot.columns]
    high_risk = snapshot[snapshot["risk_tier"] == "High Risk"]
    high_risk_cols = [c for c in HIGH_RISK_EXPORT_COLUMNS if c in high_risk.columns]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.download_button(
            "⬇️ Portfolio summary (CSV)",
            data=dataframe_to_csv_bytes(snapshot[summary_cols]),
            file_name="portfolio_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "⬇️ High-risk customers (CSV)",
            data=dataframe_to_csv_bytes(high_risk[high_risk_cols]),
            file_name="high_risk_customers.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=high_risk.empty,
        )
    with col3:
        st.download_button(
            "⬇️ Active alerts (CSV)",
            data=dataframe_to_csv_bytes(alerts),
            file_name="active_alerts.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=alerts.empty,
        )

    if st.button("💾 Save all reports to ./reports/", use_container_width=True):
        summary_path = export_summary_report(snapshot)
        high_risk_path = export_high_risk_customers(snapshot)
        alerts_path = export_alerts_report(alerts)
        st.success(
            "Saved:\n"
            f"- `{summary_path}`\n"
            f"- `{high_risk_path}`\n"
            f"- `{alerts_path}`"
        )


def render_validation_panel(validation) -> None:
    with st.expander("🔍 Data validation report", expanded=False):
        st.json(validation.to_dict())


# ---- Entrypoint -------------------------------------------------------------

def main() -> None:
    data_path = Path(DEFAULT_DATA_PATH)
    if not data_path.exists():
        st.error(
            f"Data file not found at `{data_path}`. "
            "Place `customer_health_monitoring_events.csv` under `./data/`."
        )
        st.stop()

    payload = load_pipeline(str(data_path))
    events = payload["events"]
    snapshot = payload["snapshot"]
    validation = payload["validation"]

    render_header(validation)

    filters = render_sidebar(snapshot)
    filtered_snapshot = apply_filters(snapshot, filters)
    filtered_alerts = generate_alerts(filtered_snapshot)

    if filtered_snapshot.empty:
        st.warning("No customers match the current filters - widen the cohort.")
        return

    render_top_metrics(filtered_snapshot)

    distribution = risk_distribution(filtered_snapshot)
    if not distribution.empty:
        st.markdown("##### Risk tier distribution")
        cols = st.columns(len(distribution))
        for col, (_, row) in zip(cols, distribution.iterrows()):
            col.metric(
                str(row["risk_tier"]),
                f"{row['customers']:,} customers",
                delta=_format_currency(row["revenue_at_risk_eur"]),
                delta_color="off",
            )

    render_charts(events, filtered_snapshot)
    render_tables(filtered_snapshot, filtered_alerts)
    render_exports(filtered_snapshot, filtered_alerts)
    render_validation_panel(validation)


if __name__ == "__main__":
    main()
