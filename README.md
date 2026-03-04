# ServiceNow Ops Analyzer

A self-contained CLI tool that ingests ServiceNow incident/change exports (CSV or REST API), auto-classifies tickets, detects recurring patterns, surfaces root cause clusters, and generates a plain-English ops health report.

---

## Features

| Capability | Details |
|---|---|
| **Ingest** | CSV files, JSON exports, glob patterns, directories, or live ServiceNow REST API |
| **Classify** | Rule-based keyword taxonomy + TF-IDF ML fallback for missing categories |
| **Pattern Detection** | DBSCAN clustering on TF-IDF vectors — finds recurring issue clusters without a fixed k |
| **Root Cause Analysis** | KMeans on resolution text to cluster how issues are fixed, with auto-selected k (silhouette) |
| **Health Score** | 0–100 score with deductions for open P1s, SLA breaches, aged tickets, recurring patterns |
| **Recommendations** | Actionable, prioritized recommendations mapped to detected root causes and patterns |
| **Output Formats** | HTML (styled), Markdown, Plain text, JSON |

---

## Installation

```bash
cd servicenow-ops-analyzer
pip install -r requirements.txt
```

Or install as a CLI tool:
```bash
pip install -e .
```

---

## Quick Start

### 1. Run the demo (no data needed)
```bash
python main.py demo
# Generates demo_report.html (and .md, .txt, .json)
```

### 2. Analyze a CSV export
```bash
python main.py analyze incidents.csv
python main.py analyze incidents.csv --format html -o reports/march_ops
```

### 3. Analyze multiple CSVs
```bash
python main.py analyze "exports/*.csv" --format all
```

### 4. Pull live from ServiceNow API
```bash
# With basic auth
python main.py fetch \
  --instance https://mycompany.service-now.com \
  --username admin \
  --password secret \
  --days 30 \
  --format html

# With bearer token via env var
export SNOW_TOKEN=your_bearer_token
python main.py fetch --instance https://mycompany.service-now.com --days 14

# Fetch change requests instead of incidents
python main.py fetch -i https://myco.service-now.com -t change_request --days 60
```

### 5. Save raw API data first, then analyze
```bash
python main.py fetch -i https://myco.service-now.com --save-raw -o reports/april
```

---

## Supported CSV Column Names

The tool auto-detects and normalizes these column name variants:

| Standard Name | Also Recognized As |
|---|---|
| `number` | `incident_number`, `change_number` |
| `short_description` | `title`, `short description` |
| `priority` | `severity` |
| `state` | `status`, `incident_state` |
| `opened_at` | `created`, `sys_created_on` |
| `assignment_group` | `assignment group` |
| `cmdb_ci` | `configuration_item` |
| `business_service` | `affected_service`, `service_offering` |
| `close_notes` | `resolution_notes` |
| `root_cause` | `u_root_cause`, `cause` |

Priority values like `"1 - Critical"`, `"High"`, `"P2"`, `"SEV1"` are all normalized automatically.

---

## Output

### HTML Report (`report.html`)
Full styled report with:
- Health score circle (color-coded: green/amber/red)
- Stat summary cards
- Priority & MTTR table with SLA breach %
- Category breakdown
- Recurring pattern cards (trend, keywords, affected services)
- Root cause cluster cards with recommendations
- Actionable recommendations table

### Markdown Report (`report.md`)
GitHub-flavored markdown — paste into Confluence, Notion, or a PR.

### Plain Text Report (`report.txt`)
Pipe-friendly for Slack bots, email, or terminal display.

### JSON (`report.json`)
Machine-readable output for downstream dashboards or alerting pipelines.

---

## How the Analysis Works

### Classification
1. If a ticket already has a recognized category → keep it
2. Rule-based keyword scan of `short_description + description` → fast, interpretable
3. TF-IDF + cosine similarity to labeled centroids → ML fallback (activates when ≥20 labeled tickets exist)

### Pattern Detection (DBSCAN)
- Vectorize all ticket descriptions with TF-IDF (1–2 grams)
- DBSCAN with cosine distance groups semantically similar tickets without requiring you to specify k
- Each cluster: labeled with top keywords, annotated with priority distribution, trend (increasing/stable/decreasing), recurrence estimate, affected services, and teams

### Root Cause Analysis (KMeans)
- Uses `close_notes` + `root_cause` fields (resolution text)
- K chosen automatically via silhouette score
- Each cluster mapped to actionable recommendations via keyword matching

### Health Score (0–100)
Starts at 100; deductions for:
- Each open P1 ticket (−5, capped −30)
- P1 MTTR > 4h SLA breach (−3 each, capped −20)
- Each recurring pattern cluster (−4, capped −20)
- Each ticket open > 7 days (−2, capped −15)
- % of resolved tickets with no root cause recorded (−0.1 per %, capped −10)

---

## Environment Variables

| Variable | Description |
|---|---|
| `SNOW_USERNAME` | ServiceNow username for basic auth |
| `SNOW_PASSWORD` | ServiceNow password for basic auth |
| `SNOW_TOKEN` | Bearer token (takes precedence over basic auth) |

---

## Project Structure

```
servicenow-ops-analyzer/
├── main.py              # CLI entry point (Click)
├── config.py            # Field mappings, keyword taxonomy, scoring weights
├── demo_data.py         # Synthetic data generator for testing
├── setup.py             # Package setup
├── requirements.txt
├── ingestion/
│   ├── __init__.py
│   └── loader.py        # CSV, JSON, and REST API ingestion + normalization
├── analysis/
│   ├── __init__.py
│   ├── classifier.py    # Rule-based + ML ticket classification
│   ├── patterns.py      # DBSCAN pattern detection
│   └── root_cause.py    # KMeans root cause clustering
└── reporting/
    ├── __init__.py
    └── report.py        # Health score, metrics, HTML/MD/text/JSON renderers
```

---

## Extending the Tool

### Add new category keywords
Edit `CATEGORY_KEYWORDS` in `config.py`:
```python
"ERP": ["sap", "oracle erp", "workday", "peoplesoft", "netsuite"],
```

### Adjust the health score
Edit `HEALTH_SCORE_WEIGHTS` and `MTTR_SLA_HOURS` in `config.py`.

### Add recommendation templates
Edit `RECOMMENDATION_TEMPLATES` in `analysis/root_cause.py`:
```python
(["sap", "erp", "payroll"], "Schedule ERP patching during low-usage windows with tested rollback plan."),
```

### Connect to Claude API for richer summaries
Replace `_render_text()` in `reporting/report.py` with a call to:
```python
import anthropic
client = anthropic.Anthropic()
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": f"Summarize this ops data:\n{report_json}"}]
)
```
