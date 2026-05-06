# Acme Customer Health Pipeline

> An end-to-end customer health monitoring and alerting pipeline for SaaS
> customer success teams. Built with **Python**, **Pandas**, **Plotly** and
> **Streamlit**.

The pipeline ingests raw customer-event data, validates it, scores each
account on a composite churn-risk model, raises rule-based alerts (high
churn risk, low adoption, SLA breaches, revenue at risk) and surfaces the
results in a clean, filterable Streamlit dashboard with CSV exports.

---

## 📌 Project Overview

Customer Success teams at SaaS companies juggle hundreds of accounts and
need to know - **at a glance** - which customers are slipping, why, and
what to do about it. This project turns a flat events feed into:

- A **per-customer health snapshot** (latest event + lifetime aggregates)
- A **composite churn-risk score** with Low / Medium / High tiers
- A **rule-based alert feed** with severities and recommended actions
- An **interactive dashboard** with sidebar filters, KPI cards, charts and
  tables
- **CSV exports** for downstream tools (BI, CRM, email)

## 🏛 Architecture

```
                       ┌──────────────────────────┐
                       │ data/                    │
                       │  customer_health_*.csv   │
                       └────────────┬─────────────┘
                                    │
                                    ▼
                  ┌────────────────────────────────────┐
                  │ utils/data_loader.py               │
                  │  - load_events()                   │
                  │  - validate_events()               │
                  │  - build_customer_snapshot()       │
                  └────────────────┬───────────────────┘
                                   │ snapshot DataFrame
                                   ▼
                  ┌────────────────────────────────────┐
                  │ utils/risk_engine.py               │
                  │  - compute_composite_score()       │
                  │  - classify_risk()                 │
                  │  - enrich_with_risk()              │
                  └────────────────┬───────────────────┘
                                   │ enriched snapshot
                                   ▼
            ┌──────────────────────┴───────────────────────┐
            ▼                                              ▼
┌────────────────────────┐                  ┌──────────────────────────────┐
│ utils/alert_generator  │                  │ utils/reporting.py           │
│  - generate_alerts()   │                  │  - export_summary_report()   │
│  - alerts_summary()    │                  │  - export_high_risk_*()      │
└──────────┬─────────────┘                  │  - export_alerts_report()    │
           │                                └──────────────┬───────────────┘
           ▼                                               ▼
        ┌──────────────────────────────────────────────────┐
        │ app.py  ·  Streamlit dashboard                   │
        │   KPI cards · charts · tables · CSV downloads    │
        └──────────────────────────────────────────────────┘
```

## 🧰 Tech Stack

| Layer            | Tool                |
|------------------|---------------------|
| Language         | Python 3.10+        |
| Data wrangling   | pandas, numpy       |
| Visualisation    | Plotly Express      |
| App framework    | Streamlit           |
| Packaging        | `requirements.txt`  |

## 🚀 Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/<your-org>/acme-customer-health-pipeline.git
cd acme-customer-health-pipeline

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Drop the dataset in place

The repository ships with a sample dataset at
`data/customer_health_monitoring_events.csv`. Replace it with your own
export keeping the same schema:

```
event_id, customer_id, customer_name, country, industry, subscription_plan,
account_manager, event_date, event_type, product_name, daily_active_users,
weekly_active_users, feature_usage_score, support_ticket_count,
avg_response_time_hours, customer_health_score, churn_risk_score,
renewal_probability_pct, monthly_recurring_revenue_eur, contract_value_eur,
alert_flag, alert_type, recommended_action
```

### 4. Run the dashboard

```bash
streamlit run app.py
```

Streamlit will print a local URL (default http://localhost:8501) - open
it in your browser.

## ✨ Features

### Data validation (`utils/data_loader.py`)
- Required-column check
- Missing-value counts per column
- Score-range validation (0-100 for `feature_usage_score`,
  `customer_health_score`, `churn_risk_score`, `renewal_probability_pct`)
- Duplicate detection on `event_id` and `(customer_id, event_date)`
- Returns a structured `ValidationReport`

### Risk engine (`utils/risk_engine.py`)
Composite churn-risk score (0-100) blends four signals:

| Signal                  | Weight | Direction          |
|-------------------------|--------|--------------------|
| `churn_risk_score`      | 0.45   | higher is worse    |
| `feature_usage_score`   | 0.25   | inverted (100 - x) |
| `support_ticket_count`  | 0.20   | capped at 20, scaled to 100 |
| `customer_health_score` | 0.10   | inverted (100 - x) |

Tiers:
- **Low Risk** (< 35)
- **Medium Risk** (35 - 59)
- **High Risk** (>= 60)

Also computes **`revenue_at_risk_eur`** = `MRR * (composite_score / 100)`.

### Alerts (`utils/alert_generator.py`)

| Alert                  | Trigger                                                                |
|------------------------|------------------------------------------------------------------------|
| **High Churn Risk**    | composite risk score ≥ 60                                              |
| **Low Product Adoption** | `feature_usage_score` ≤ 40                                            |
| **SLA Breach**         | `avg_response_time_hours` > 24 OR `support_ticket_count` ≥ 8           |
| **Revenue at Risk**    | `monthly_recurring_revenue_eur` ≥ 10,000 AND `renewal_probability_pct` < 60 |

Each alert carries a severity (`Critical` / `High`) and a recommended
action so the support / CS team can act immediately.

### Dashboard (`app.py`)

**Top metrics**
- Total Customers
- Average Health Score
- High-Risk Customers (with % of book)
- Revenue at Risk (EUR)

**Charts (Plotly)**
- Health Score Distribution (stacked by risk tier)
- Average Churn Risk by Country
- Feature Usage Trends (monthly, per product)
- Revenue at Risk by Subscription Plan
- Support Tickets vs Health Score (bubble size = MRR)

**Tables**
- Top 15 Risk Customers
- Active Alerts feed
- Recommended Actions per customer

**Sidebar filters**
- Country, Industry, Subscription Plan, Account Manager, Risk Tier
- Health-score range slider

### Report exports (`utils/reporting.py`)
- One-click download buttons for portfolio summary, high-risk customers and
  active alerts
- "Save all reports to ./reports/" button to persist time-stamped CSVs

## 📁 Project structure

```
acme-customer-health-pipeline/
├── app.py                       # Streamlit entrypoint
├── requirements.txt
├── README.md
├── .gitignore
├── data/
│   └── customer_health_monitoring_events.csv
├── reports/                     # generated CSVs land here
└── utils/
    ├── __init__.py
    ├── data_loader.py
    ├── risk_engine.py
    ├── alert_generator.py
    └── reporting.py
```

## 🖼 Screenshots

> Drop dashboard screenshots into `docs/screenshots/` and reference them
> here. Suggested captures:

| View                     | Path                                              |
|--------------------------|---------------------------------------------------|
| Header & KPIs            | `docs/screenshots/01_overview.png`                |
| Charts                   | `docs/screenshots/02_charts.png`                  |
| Active alerts            | `docs/screenshots/03_alerts.png`                  |
| Top risk customers table | `docs/screenshots/04_top_risk.png`                |

```markdown
![Overview](docs/screenshots/01_overview.png)
![Charts](docs/screenshots/02_charts.png)
![Alerts](docs/screenshots/03_alerts.png)
![Top Risk](docs/screenshots/04_top_risk.png)
```

## 🧪 Quick sanity check (no Streamlit)

```bash
python -c "
from utils.data_loader import load_events, validate_events, build_customer_snapshot
from utils.risk_engine import enrich_with_risk, summarise_portfolio
from utils.alert_generator import generate_alerts

events = load_events()
print('validation:', validate_events(events).to_dict())
snap = enrich_with_risk(build_customer_snapshot(events))
print('portfolio:', summarise_portfolio(snap))
print('alerts:', len(generate_alerts(snap)))
"
```

## 🛣 Roadmap

- Email/Slack delivery of alerts
- Historical risk-tier transitions (week-over-week)
- ML-based risk scoring with feature importance
- Snowflake / BigQuery loaders alongside the CSV reader

## 📄 License

MIT - see `LICENSE` (add your preferred license file before publishing).
