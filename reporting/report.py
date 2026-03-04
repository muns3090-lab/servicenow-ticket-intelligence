"""
Report generation: compute health metrics and render to HTML, Markdown,
and plain text.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import HEALTH_SCORE_WEIGHTS, MTTR_SLA_HOURS


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------

def _health_score(df: pd.DataFrame, patterns: dict, root_causes: dict) -> int:
    """Compute an ops health score 0-100 (100 = perfect)."""
    score = 100.0
    w = HEALTH_SCORE_WEIGHTS

    open_states = {"New", "In Progress", "On Hold"}
    open_df = df[df["state"].isin(open_states)]

    # P1 open tickets
    p1_open = int((open_df["priority"] == "P1").sum())
    score -= min(p1_open * w["p1_open_per_ticket"], 30)

    # P1 MTTR breaches
    p1_resolved = df[df["priority"] == "P1"].copy()
    p1_breach = int(
        (p1_resolved["mttr_hours"].dropna() > MTTR_SLA_HOURS["P1"]).sum()
    )
    score -= min(p1_breach * w["p1_breach_per_ticket"], 20)

    # Recurring patterns
    n_patterns = len(patterns.get("clusters", []))
    score -= min(n_patterns * w["recurring_pattern"], 20)

    # Tickets open > 7 days
    aged = int((open_df.get("age_hours", pd.Series(dtype=float)).dropna() > 168).sum())
    score -= min(aged * w["unresolved_7d"], 15)

    # Tickets with no root cause (among resolved)
    resolved_df = df[~df["state"].isin(open_states)]
    if not resolved_df.empty:
        no_rc_rate = float(
            (resolved_df["root_cause"].fillna("").str.strip() == "").sum()
        ) / len(resolved_df) * 100
        score -= min(no_rc_rate * w["no_root_cause_rate"], 10)

    return max(0, math.floor(score))


def _score_label(score: int) -> tuple[str, str]:
    """Return (label, css_color) for a health score."""
    if score >= 85:
        return "Healthy", "#22c55e"
    if score >= 65:
        return "Fair", "#f59e0b"
    if score >= 40:
        return "At Risk", "#ef4444"
    return "Critical", "#7f1d1d"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _calculate_metrics(df: pd.DataFrame) -> dict[str, Any]:
    open_states = {"New", "In Progress", "On Hold"}
    open_df = df[df["state"].isin(open_states)]
    resolved_df = df[~df["state"].isin(open_states)]

    # Volume by priority
    priority_counts = df["priority"].value_counts().to_dict()

    # MTTR per priority
    mttr = {}
    for p in ["P1", "P2", "P3", "P4"]:
        vals = df[df["priority"] == p]["mttr_hours"].dropna()
        if not vals.empty:
            mttr[p] = {
                "avg": round(vals.mean(), 1),
                "median": round(vals.median(), 1),
                "sla_hours": MTTR_SLA_HOURS.get(p),
                "breach_pct": round(
                    (vals > MTTR_SLA_HOURS.get(p, 9999)).mean() * 100, 1
                ),
            }

    # Category breakdown
    cat_counts = df["category"].value_counts().head(10).to_dict()

    # Assignment group breakdown
    group_counts = df["assignment_group"].value_counts().head(8).to_dict()

    # State breakdown
    state_counts = df["state"].value_counts().to_dict()

    # Record type breakdown
    type_counts = df["record_type"].value_counts().to_dict()

    # Time range
    time_range_start = df["opened_at"].min()
    time_range_end = df["opened_at"].max()

    return {
        "total": len(df),
        "open": int(len(open_df)),
        "resolved": int(len(resolved_df)),
        "p1_open": int((open_df["priority"] == "P1").sum()),
        "p1_total": int((df["priority"] == "P1").sum()),
        "priority_counts": priority_counts,
        "mttr": mttr,
        "category_counts": cat_counts,
        "group_counts": group_counts,
        "state_counts": state_counts,
        "type_counts": type_counts,
        "time_range_start": time_range_start,
        "time_range_end": time_range_end,
        "no_root_cause_pct": round(
            (resolved_df["root_cause"].fillna("").str.strip() == "").mean() * 100, 1
        ) if not resolved_df.empty else 0,
    }


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _generate_recommendations(
    df: pd.DataFrame,
    metrics: dict,
    patterns: dict,
    root_causes: dict,
) -> list[dict[str, str]]:
    recs = []

    # P1 SLA breaches
    if metrics["mttr"].get("P1", {}).get("breach_pct", 0) > 20:
        recs.append({
            "priority": "High",
            "finding": f"P1 SLA breached {metrics['mttr']['P1']['breach_pct']}% of the time",
            "action": "Review P1 escalation path, on-call coverage, and runbook completeness.",
        })

    # Many open P1s
    if metrics["p1_open"] >= 2:
        recs.append({
            "priority": "High",
            "finding": f"{metrics['p1_open']} P1 ticket(s) currently open",
            "action": "Escalate open P1 incidents immediately; conduct a bridge call if multiple services affected.",
        })

    # Recurring patterns
    for pat in patterns.get("clusters", [])[:3]:
        if pat["size"] >= 5:
            recs.append({
                "priority": "Medium",
                "finding": f"Recurring pattern: '{pat['label']}' ({pat['size']} tickets, trend: {pat['trend']})",
                "action": (
                    f"Open a Problem ticket to address root cause. "
                    f"Top keywords: {', '.join(pat['keywords'][:3])}. "
                    + (f"Primarily affects: {', '.join(pat['top_services'][:2])}." if pat['top_services'] else "")
                ),
            })

    # Root cause recommendations
    for rc in root_causes.get("root_causes", [])[:3]:
        for r in rc.get("recommendations", []):
            recs.append({
                "priority": "Medium",
                "finding": f"Root cause cluster: '{rc['label']}' ({rc['ticket_count']} tickets)",
                "action": r,
            })

    # High no-root-cause rate
    if metrics["no_root_cause_pct"] > 40:
        recs.append({
            "priority": "Low",
            "finding": f"{metrics['no_root_cause_pct']}% of resolved tickets have no root cause recorded",
            "action": "Enforce root cause capture in closure workflow; add mandatory field to ticket resolution form.",
        })

    # Aged open tickets
    aged = int((df[df["state"].isin({"New","In Progress","On Hold"})].get("age_hours", pd.Series(dtype=float)).dropna() > 168).sum())
    if aged > 0:
        recs.append({
            "priority": "Medium",
            "finding": f"{aged} ticket(s) open for more than 7 days",
            "action": "Trigger weekly aging ticket review with team leads. Set automated escalation at 5-day mark.",
        })

    # De-duplicate and limit
    seen = set()
    unique_recs = []
    for r in recs:
        key = r["action"][:60]
        if key not in seen:
            seen.add(key)
            unique_recs.append(r)

    return unique_recs[:10]


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Assemble the full ops health report and render to multiple formats."""

    def generate(
        self,
        df: pd.DataFrame,
        pattern_result: dict[str, Any],
        rc_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute all report data and return as a dict."""
        metrics = _calculate_metrics(df)
        score = _health_score(df, pattern_result, rc_result)
        score_label, score_color = _score_label(score)
        recs = _generate_recommendations(df, metrics, pattern_result, rc_result)

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        return {
            "generated_at": generated_at,
            "health_score": score,
            "health_label": score_label,
            "health_color": score_color,
            "metrics": metrics,
            "patterns": pattern_result,
            "root_causes": rc_result,
            "recommendations": recs,
        }

    # ------------------------------------------------------------------

    def to_html(self, report: dict[str, Any], output_path: str) -> None:
        html = _render_html(report)
        Path(output_path).write_text(html, encoding="utf-8")

    def to_markdown(self, report: dict[str, Any], output_path: str) -> None:
        md = _render_markdown(report)
        Path(output_path).write_text(md, encoding="utf-8")

    def to_text(self, report: dict[str, Any], output_path: str) -> None:
        txt = _render_text(report)
        Path(output_path).write_text(txt, encoding="utf-8")

    def to_json(self, report: dict[str, Any], output_path: str) -> None:
        def _serial(obj):
            if isinstance(obj, (pd.Timestamp,)):
                return str(obj)
            if isinstance(obj, float) and math.isnan(obj):
                return None
            raise TypeError(f"Not serializable: {type(obj)}")
        Path(output_path).write_text(
            json.dumps(report, indent=2, default=_serial), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _fmt_ts(ts) -> str:
    if ts is None or (isinstance(ts, float) and math.isnan(ts)):
        return "N/A"
    try:
        if hasattr(ts, "strftime"):
            return ts.strftime("%Y-%m-%d")
    except Exception:
        pass
    return str(ts)


def _priority_badge(p: str) -> str:
    colors = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#3b82f6"}
    bg = colors.get(p, "#6b7280")
    return f'<span style="background:{bg};color:#fff;padding:2px 8px;border-radius:9999px;font-size:0.75rem;font-weight:600">{p}</span>'


def _render_html(r: dict[str, Any]) -> str:
    m = r["metrics"]
    patterns = r["patterns"].get("clusters", [])
    rcs = r["root_causes"].get("root_causes", [])
    recs = r["recommendations"]
    score = r["health_score"]
    color = r["health_color"]
    label = r["health_label"]

    # Priority summary rows
    priority_rows = ""
    for p in ["P1", "P2", "P3", "P4", "Unknown"]:
        cnt = m["priority_counts"].get(p, 0)
        if cnt == 0:
            continue
        mttr_info = m["mttr"].get(p, {})
        avg_mttr = f"{mttr_info.get('avg','—')}h" if mttr_info else "—"
        sla_breach = f"{mttr_info.get('breach_pct','—')}%" if mttr_info else "—"
        priority_rows += f"""
        <tr>
          <td><strong>{p}</strong></td>
          <td>{cnt}</td>
          <td>{avg_mttr}</td>
          <td>{sla_breach}</td>
        </tr>"""

    # Category rows
    cat_rows = "".join(
        f"<tr><td>{cat}</td><td>{cnt}</td></tr>"
        for cat, cnt in list(m["category_counts"].items())[:8]
    )

    # Pattern cards
    pattern_cards = ""
    for pat in patterns[:6]:
        trend_icon = {"Increasing": "↑", "Decreasing": "↓", "Stable": "→"}.get(pat["trend"], "")
        trend_color = {"Increasing": "#ef4444", "Decreasing": "#22c55e", "Stable": "#6b7280"}.get(pat["trend"], "#6b7280")
        kw_tags = "".join(
            f'<span style="background:#e0f2fe;color:#0369a1;padding:2px 6px;border-radius:4px;font-size:0.75rem;margin:2px">{k}</span>'
            for k in pat["keywords"][:5]
        )
        services = ", ".join(pat["top_services"]) or "—"
        groups = ", ".join(pat["top_groups"]) or "—"
        pattern_cards += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h4 style="margin:0;color:#1e293b">{pat['label']}</h4>
            <span style="font-size:0.85rem;color:{trend_color};font-weight:600">{trend_icon} {pat['trend']} &nbsp;|&nbsp; {pat['recurrence']}</span>
          </div>
          <p style="margin:6px 0;color:#64748b;font-size:0.85rem">
            <strong>{pat['size']}</strong> tickets &nbsp;|&nbsp;
            P1: {pat['priority_dist'].get('P1',0)} &nbsp;
            P2: {pat['priority_dist'].get('P2',0)} &nbsp;
            P3: {pat['priority_dist'].get('P3',0)} &nbsp;|&nbsp;
            First: {_fmt_ts(pat['first_seen'])} &nbsp; Last: {_fmt_ts(pat['last_seen'])}
          </p>
          <p style="margin:4px 0;font-size:0.8rem;color:#475569">
            <strong>Services:</strong> {services} &nbsp;|&nbsp;
            <strong>Teams:</strong> {groups}
            {f"&nbsp;|&nbsp; <strong>Avg MTTR:</strong> {pat['avg_mttr_hours']}h" if pat['avg_mttr_hours'] else ""}
          </p>
          <div style="margin-top:8px">{kw_tags}</div>
        </div>"""

    if not pattern_cards:
        pattern_cards = '<p style="color:#64748b">No significant recurring patterns detected.</p>'

    # Root cause cards
    rc_cards = ""
    for rc in rcs[:5]:
        kw_tags = "".join(
            f'<span style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:4px;font-size:0.75rem;margin:2px">{k}</span>'
            for k in rc["keywords"][:5]
        )
        rec_list = "".join(f"<li>{rec}</li>" for rec in rc["recommendations"])
        rc_cards += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px">
          <h4 style="margin:0 0 6px 0;color:#1e293b">{rc['label']}</h4>
          <p style="margin:4px 0;color:#64748b;font-size:0.85rem">
            <strong>{rc['ticket_count']}</strong> tickets with this root cause
            {f"&nbsp;|&nbsp; Avg MTTR: {rc['avg_mttr_hours']}h" if rc['avg_mttr_hours'] else ""}
          </p>
          <div style="margin:8px 0">{kw_tags}</div>
          {f'<ul style="margin:8px 0;padding-left:1.2em;font-size:0.85rem;color:#374151">{rec_list}</ul>' if rec_list else ''}
        </div>"""

    if not rc_cards:
        rc_cards = '<p style="color:#64748b">Insufficient resolution data for root cause clustering.</p>'

    # Recommendations
    rec_rows = ""
    for rec in recs:
        rec_rows += f"""
        <tr style="border-bottom:1px solid #f1f5f9">
          <td style="padding:10px 12px;vertical-align:top">{_priority_badge(rec['priority'])}</td>
          <td style="padding:10px 12px;vertical-align:top;color:#374151">{rec['finding']}</td>
          <td style="padding:10px 12px;vertical-align:top;color:#1e293b">{rec['action']}</td>
        </tr>"""

    if not rec_rows:
        rec_rows = '<tr><td colspan="3" style="padding:12px;color:#64748b">No recommendations generated.</td></tr>'

    # Stat cards
    def stat_card(title, value, subtitle="", color="#3b82f6"):
        return f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;text-align:center;min-width:130px">
          <div style="font-size:2rem;font-weight:700;color:{color}">{value}</div>
          <div style="font-size:0.85rem;font-weight:600;color:#374151;margin-top:2px">{title}</div>
          {f'<div style="font-size:0.75rem;color:#9ca3af;margin-top:2px">{subtitle}</div>' if subtitle else ''}
        </div>"""

    p1_color = "#ef4444" if m["p1_open"] > 0 else "#22c55e"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Ops Health Report — {r['generated_at']}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f8fafc; color:#1e293b; }}
  .page {{ max-width:1100px; margin:0 auto; padding:32px 20px; }}
  h1 {{ font-size:1.75rem; font-weight:700; color:#0f172a; }}
  h2 {{ font-size:1.25rem; font-weight:700; color:#1e293b; margin:28px 0 14px 0; padding-bottom:6px; border-bottom:2px solid #e2e8f0; }}
  h3 {{ font-size:1.05rem; font-weight:600; color:#334155; margin:20px 0 10px 0; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; border:1px solid #e5e7eb; }}
  th {{ background:#f8fafc; padding:10px 12px; text-align:left; font-size:0.8rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.05em; }}
  td {{ padding:9px 12px; font-size:0.875rem; border-top:1px solid #f1f5f9; }}
  .score-circle {{ width:100px; height:100px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-direction:column; border:4px solid {color}; }}
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:28px;flex-wrap:wrap;gap:16px">
    <div>
      <h1>Ops Health Report</h1>
      <p style="color:#64748b;margin-top:4px">Generated: {r['generated_at']} &nbsp;|&nbsp;
        Period: {_fmt_ts(m['time_range_start'])} → {_fmt_ts(m['time_range_end'])}
      </p>
    </div>
    <div style="text-align:center">
      <div class="score-circle">
        <span style="font-size:2rem;font-weight:700;color:{color}">{score}</span>
        <span style="font-size:0.7rem;font-weight:600;color:{color}">{label}</span>
      </div>
      <div style="font-size:0.75rem;color:#6b7280;margin-top:4px">Health Score</div>
    </div>
  </div>

  <!-- Stat cards -->
  <div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:28px">
    {stat_card("Total Tickets", m["total"])}
    {stat_card("Open", m["open"], "currently active", "#f59e0b")}
    {stat_card("P1 Open", m["p1_open"], "critical", p1_color)}
    {stat_card("Resolved", m["resolved"], "", "#22c55e")}
    {stat_card("Patterns", len(r["patterns"].get("clusters", [])), "recurring clusters", "#8b5cf6")}
    {stat_card("Root Causes", len(r["root_causes"].get("root_causes", [])), "identified", "#0ea5e9")}
  </div>

  <!-- Unresolved insight -->
  <div style="background:#fefce8;border:1px solid #fde68a;border-radius:8px;padding:14px 16px;margin-bottom:24px;font-size:0.9rem;color:#713f12">
    <strong>Open Ticket Status:</strong> {r['root_causes'].get('unresolved_insight', '')}
  </div>

  <!-- Priority & MTTR -->
  <h2>Priority Breakdown & MTTR</h2>
  <table>
    <thead><tr>
      <th>Priority</th><th>Total Tickets</th><th>Avg MTTR</th><th>SLA Breach %</th>
    </tr></thead>
    <tbody>{priority_rows}</tbody>
  </table>

  <!-- Category breakdown -->
  <h2>Category Breakdown</h2>
  <table>
    <thead><tr><th>Category</th><th>Ticket Count</th></tr></thead>
    <tbody>{cat_rows}</tbody>
  </table>

  <!-- Recurring Patterns -->
  <h2>Recurring Patterns ({len(patterns)} clusters detected)</h2>
  {pattern_cards}

  <!-- Root Cause Clusters -->
  <h2>Root Cause Clusters</h2>
  {rc_cards}

  <!-- Actionable Recommendations -->
  <h2>Actionable Recommendations</h2>
  <table>
    <thead><tr><th style="width:90px">Priority</th><th>Finding</th><th>Recommended Action</th></tr></thead>
    <tbody>{rec_rows}</tbody>
  </table>

  <!-- Footer -->
  <div style="margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:0.75rem;text-align:center">
    ServiceNow Ops Analyzer &nbsp;|&nbsp; {r['generated_at']}
  </div>

</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _render_markdown(r: dict[str, Any]) -> str:
    m = r["metrics"]
    patterns = r["patterns"].get("clusters", [])
    rcs = r["root_causes"].get("root_causes", [])
    recs = r["recommendations"]
    score = r["health_score"]
    label = r["health_label"]

    lines = [
        f"# Ops Health Report",
        f"",
        f"**Generated:** {r['generated_at']}  ",
        f"**Period:** {_fmt_ts(m['time_range_start'])} → {_fmt_ts(m['time_range_end'])}  ",
        f"**Health Score:** {score}/100 — {label}",
        f"",
        f"---",
        f"",
        f"## Executive Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Tickets | {m['total']} |",
        f"| Open | {m['open']} |",
        f"| P1 Open | {m['p1_open']} |",
        f"| Resolved | {m['resolved']} |",
        f"| Recurring Patterns | {len(patterns)} |",
        f"| Root Cause Clusters | {len(rcs)} |",
        f"| Tickets w/o Root Cause | {m['no_root_cause_pct']}% |",
        f"",
        f"> **Open Ticket Status:** {r['root_causes'].get('unresolved_insight', '')}",
        f"",
        f"---",
        f"",
        f"## Priority Breakdown & MTTR",
        f"",
        f"| Priority | Count | Avg MTTR | SLA Breach |",
        f"|----------|-------|----------|------------|",
    ]

    for p in ["P1", "P2", "P3", "P4", "Unknown"]:
        cnt = m["priority_counts"].get(p, 0)
        if cnt == 0:
            continue
        mttr_info = m["mttr"].get(p, {})
        avg_mttr = f"{mttr_info.get('avg','—')}h" if mttr_info else "—"
        breach = f"{mttr_info.get('breach_pct','—')}%" if mttr_info else "—"
        lines.append(f"| {p} | {cnt} | {avg_mttr} | {breach} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Recurring Patterns ({len(patterns)} clusters)",
        f"",
    ]

    for i, pat in enumerate(patterns[:8], 1):
        services = ", ".join(pat["top_services"]) or "—"
        groups = ", ".join(pat["top_groups"]) or "—"
        kws = ", ".join(pat["keywords"][:5])
        lines += [
            f"### {i}. {pat['label']}",
            f"",
            f"- **Tickets:** {pat['size']} &nbsp; **Trend:** {pat['trend']} &nbsp; **Recurrence:** {pat['recurrence']}",
            f"- **P1/P2/P3:** {pat['priority_dist'].get('P1',0)} / {pat['priority_dist'].get('P2',0)} / {pat['priority_dist'].get('P3',0)}",
            f"- **First seen:** {_fmt_ts(pat['first_seen'])} &nbsp; **Last seen:** {_fmt_ts(pat['last_seen'])}",
            f"- **Affected services:** {services}",
            f"- **Teams:** {groups}",
            f"- **Keywords:** `{kws}`",
            f"",
        ]

    if not patterns:
        lines.append("No significant recurring patterns detected.\n")

    lines += [
        f"---",
        f"",
        f"## Root Cause Clusters",
        f"",
    ]

    for i, rc in enumerate(rcs[:6], 1):
        kws = ", ".join(rc["keywords"][:5])
        lines += [
            f"### {i}. {rc['label']}",
            f"",
            f"- **Tickets:** {rc['ticket_count']}",
            f"- **Keywords:** `{kws}`",
        ]
        if rc["recommendations"]:
            lines.append("- **Recommendations:**")
            for rec in rc["recommendations"]:
                lines.append(f"  - {rec}")
        lines.append("")

    if not rcs:
        lines.append("Insufficient resolution data for root cause clustering.\n")

    lines += [
        f"---",
        f"",
        f"## Actionable Recommendations",
        f"",
        f"| # | Priority | Finding | Action |",
        f"|---|----------|---------|--------|",
    ]
    for i, rec in enumerate(recs, 1):
        finding = rec["finding"].replace("|", "\\|")
        action = rec["action"].replace("|", "\\|")
        lines.append(f"| {i} | **{rec['priority']}** | {finding} | {action} |")

    if not recs:
        lines.append("No recommendations generated.")

    lines += [
        f"",
        f"---",
        f"",
        f"*ServiceNow Ops Analyzer — {r['generated_at']}*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plain text renderer
# ---------------------------------------------------------------------------

def _render_text(r: dict[str, Any]) -> str:
    m = r["metrics"]
    patterns = r["patterns"].get("clusters", [])
    rcs = r["root_causes"].get("root_causes", [])
    recs = r["recommendations"]

    sep = "=" * 70
    thin = "-" * 70

    lines = [
        sep,
        "  OPS HEALTH REPORT",
        f"  Generated: {r['generated_at']}",
        f"  Period:    {_fmt_ts(m['time_range_start'])} → {_fmt_ts(m['time_range_end'])}",
        f"  Health Score: {r['health_score']}/100 — {r['health_label']}",
        sep,
        "",
        "SUMMARY",
        thin,
        f"  Total Tickets:        {m['total']}",
        f"  Currently Open:       {m['open']}",
        f"  P1 (Critical) Open:   {m['p1_open']}",
        f"  Resolved:             {m['resolved']}",
        f"  Recurring Patterns:   {len(patterns)}",
        f"  Root Cause Clusters:  {len(rcs)}",
        f"  No Root Cause:        {m['no_root_cause_pct']}% of resolved",
        "",
        f"  {r['root_causes'].get('unresolved_insight', '')}",
        "",
        "PRIORITY BREAKDOWN & MTTR",
        thin,
        f"  {'Priority':<12} {'Count':<8} {'Avg MTTR':<12} {'SLA Breach'}",
        f"  {'--------':<12} {'-----':<8} {'--------':<12} {'----------'}",
    ]

    for p in ["P1", "P2", "P3", "P4", "Unknown"]:
        cnt = m["priority_counts"].get(p, 0)
        if cnt == 0:
            continue
        mttr_info = m["mttr"].get(p, {})
        avg_mttr = f"{mttr_info.get('avg','—')}h" if mttr_info else "—"
        breach = f"{mttr_info.get('breach_pct','—')}%" if mttr_info else "—"
        lines.append(f"  {p:<12} {cnt:<8} {avg_mttr:<12} {breach}")

    lines += [
        "",
        f"RECURRING PATTERNS ({len(patterns)} CLUSTERS)",
        thin,
    ]

    for i, pat in enumerate(patterns[:6], 1):
        services = ", ".join(pat["top_services"]) or "none"
        kws = ", ".join(pat["keywords"][:4])
        lines += [
            f"  {i}. {pat['label']}",
            f"     Tickets: {pat['size']}  |  Trend: {pat['trend']}  |  {pat['recurrence']}",
            f"     P1/P2/P3: {pat['priority_dist'].get('P1',0)}/{pat['priority_dist'].get('P2',0)}/{pat['priority_dist'].get('P3',0)}",
            f"     Services: {services}",
            f"     Keywords: {kws}",
            "",
        ]

    if not patterns:
        lines.append("  No significant recurring patterns detected.\n")

    lines += [
        f"ROOT CAUSE CLUSTERS ({len(rcs)} FOUND)",
        thin,
    ]

    for i, rc in enumerate(rcs[:5], 1):
        kws = ", ".join(rc["keywords"][:4])
        lines += [
            f"  {i}. {rc['label']}  ({rc['ticket_count']} tickets)",
            f"     Keywords: {kws}",
        ]
        for rec in rc.get("recommendations", []):
            lines.append(f"     → {rec}")
        lines.append("")

    if not rcs:
        lines.append("  Insufficient resolution data.\n")

    lines += [
        f"ACTIONABLE RECOMMENDATIONS",
        thin,
    ]

    for i, rec in enumerate(recs, 1):
        lines += [
            f"  {i}. [{rec['priority'].upper()}] {rec['finding']}",
            f"     Action: {rec['action']}",
            "",
        ]

    if not recs:
        lines.append("  No recommendations generated.\n")

    lines.append(sep)
    return "\n".join(lines)
