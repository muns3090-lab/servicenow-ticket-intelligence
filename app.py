"""
ServiceNow Ops Analyzer — Streamlit web UI.

Upload a CSV export, run the full analysis pipeline, and view the ops health
report directly in the browser.
"""

from __future__ import annotations

import io
import json
import math
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ingestion import DataLoader
from analysis import TicketClassifier, PatternDetector, RootCauseAnalyzer
from reporting import ReportGenerator
from reporting.report import _render_html, _render_markdown, _render_text

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ServiceNow Ops Analyzer",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("ServiceNow Ops Analyzer")
st.markdown(
    "Upload a ServiceNow CSV export to classify tickets, detect recurring patterns, "
    "identify root causes, and generate an ops health report."
)

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

uploaded_file = st.file_uploader(
    "Upload ServiceNow CSV export",
    type=["csv"],
    help="Export your incidents, changes, or problems table from ServiceNow as a CSV file.",
)

if uploaded_file is None:
    st.info("Upload a CSV file above to get started.")
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with st.spinner("Loading CSV…"):
    loader = DataLoader()
    try:
        # Write upload to a temp file so DataLoader can read it normally
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        df = loader.load_csv(tmp_path)
    except Exception as exc:
        st.error(f"Failed to load CSV: {exc}")
        st.stop()

if df.empty:
    st.warning("No records found in the uploaded file. Check the file format and column names.")
    st.stop()

st.success(f"Loaded **{len(df):,}** tickets from `{uploaded_file.name}`.")

# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

progress_bar = st.progress(0, text="Starting analysis…")

try:
    progress_bar.progress(10, text="Classifying tickets…")
    clf = TicketClassifier()
    df = clf.fit_classify(df)

    progress_bar.progress(40, text="Detecting recurring patterns…")
    detector = PatternDetector()
    pattern_result = detector.detect(df)
    df = pattern_result.pop("df_with_cluster")

    progress_bar.progress(65, text="Analyzing root causes…")
    rc_analyzer = RootCauseAnalyzer()
    rc_result = rc_analyzer.analyze(df, pattern_result)

    progress_bar.progress(85, text="Generating report…")
    gen = ReportGenerator()
    report = gen.generate(df, pattern_result, rc_result)

    progress_bar.progress(100, text="Done.")
except Exception as exc:
    st.error(f"Analysis failed: {exc}")
    st.exception(exc)
    st.stop()

progress_bar.empty()

# ---------------------------------------------------------------------------
# Summary metrics (native Streamlit widgets)
# ---------------------------------------------------------------------------

score = report["health_score"]
label = report["health_label"]
color = report["health_color"]
m = report["metrics"]
patterns = report["patterns"].get("clusters", [])
rcs = report["root_causes"].get("root_causes", [])
recs = report["recommendations"]

# Health score banner
score_colors = {
    "Healthy": "green",
    "Fair": "orange",
    "At Risk": "red",
    "Critical": "red",
}
banner_color = score_colors.get(label, "gray")
st.markdown(
    f"""
    <div style="background:{color}18;border-left:6px solid {color};
                border-radius:6px;padding:16px 20px;margin-bottom:20px">
      <span style="font-size:2rem;font-weight:700;color:{color}">{score}/100</span>
      <span style="font-size:1.2rem;font-weight:600;color:{color};margin-left:12px">{label}</span>
      <span style="font-size:0.85rem;color:#64748b;margin-left:20px">Generated {report['generated_at']}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total Tickets", f"{m['total']:,}")
col2.metric("Open", f"{m['open']:,}")
col3.metric("P1 Open", f"{m['p1_open']:,}", delta=None if m["p1_open"] == 0 else f"{m['p1_open']} critical", delta_color="inverse")
col4.metric("Resolved", f"{m['resolved']:,}")
col5.metric("Patterns", len(patterns))
col6.metric("Root Causes", len(rcs))

st.divider()

# ---------------------------------------------------------------------------
# Tabs: full HTML report | recommendations | raw data
# ---------------------------------------------------------------------------

tab_report, tab_recs, tab_data = st.tabs(["Full Report", "Recommendations", "Raw Data Preview"])

with tab_report:
    html_str = _render_html(report)
    # Render inside a scrollable iframe-like component
    components.html(html_str, height=900, scrolling=True)

with tab_recs:
    if not recs:
        st.info("No recommendations generated.")
    else:
        for rec in recs:
            pri = rec["priority"]
            icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(pri, "⚪")
            with st.expander(f"{icon} [{pri}] {rec['finding']}"):
                st.markdown(f"**Recommended Action:** {rec['action']}")

with tab_data:
    st.markdown(f"Showing first 200 rows of the normalized dataset ({len(df):,} total).")
    display_cols = [
        "number", "short_description", "priority", "state",
        "category", "assignment_group", "opened_at", "mttr_hours",
    ]
    show_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[show_cols].head(200), use_container_width=True)

# ---------------------------------------------------------------------------
# Download buttons
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Download Report")

dl1, dl2, dl3 = st.columns(3)

with dl1:
    st.download_button(
        label="Download HTML",
        data=_render_html(report).encode("utf-8"),
        file_name="ops_health_report.html",
        mime="text/html",
    )

with dl2:
    st.download_button(
        label="Download Markdown",
        data=_render_markdown(report).encode("utf-8"),
        file_name="ops_health_report.md",
        mime="text/markdown",
    )

with dl3:
    def _json_serial(obj):
        if isinstance(obj, pd.Timestamp):
            return str(obj)
        if isinstance(obj, float) and math.isnan(obj):
            return None
        raise TypeError(f"Not serializable: {type(obj)}")

    st.download_button(
        label="Download JSON",
        data=json.dumps(report, indent=2, default=_json_serial).encode("utf-8"),
        file_name="ops_health_report.json",
        mime="application/json",
    )
