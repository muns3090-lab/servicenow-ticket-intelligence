#!/usr/bin/env python3
"""
ServiceNow Ops Analyzer — CLI entry point.

Commands:
  analyze   Analyze a CSV / JSON export and produce a report.
  fetch     Pull tickets live from the ServiceNow REST API and analyze.
  demo      Generate a synthetic dataset and run a full demo analysis.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich import box

from ingestion import DataLoader
from analysis import TicketClassifier, PatternDetector, RootCauseAnalyzer
from reporting import ReportGenerator

console = Console()


# ---------------------------------------------------------------------------
# Shared pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(df, output_stem: str, fmt: str, quiet: bool, days_label: str = ""):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        t1 = progress.add_task("Classifying tickets …", total=None)
        clf = TicketClassifier()
        df = clf.fit_classify(df)
        progress.update(t1, completed=True, description="[green]Classification done")

        t2 = progress.add_task("Detecting patterns …", total=None)
        detector = PatternDetector()
        pattern_result = detector.detect(df)
        df = pattern_result.pop("df_with_cluster")
        progress.update(t2, completed=True, description="[green]Patterns detected")

        t3 = progress.add_task("Analyzing root causes …", total=None)
        rc_analyzer = RootCauseAnalyzer()
        rc_result = rc_analyzer.analyze(df, pattern_result)
        progress.update(t3, completed=True, description="[green]Root causes analyzed")

        t4 = progress.add_task("Generating report …", total=None)
        gen = ReportGenerator()
        report = gen.generate(df, pattern_result, rc_result)
        progress.update(t4, completed=True, description="[green]Report ready")

    # Print terminal summary
    if not quiet:
        _print_summary(report, console)

    # Write outputs
    output_stem = Path(output_stem)
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    written = []

    formats = [fmt] if fmt != "all" else ["html", "md", "text", "json"]
    for f in formats:
        if f == "html":
            p = str(output_stem) + ".html"
            gen.to_html(report, p); written.append(p)
        elif f in ("md", "markdown"):
            p = str(output_stem) + ".md"
            gen.to_markdown(report, p); written.append(p)
        elif f in ("text", "txt"):
            p = str(output_stem) + ".txt"
            gen.to_text(report, p); written.append(p)
        elif f == "json":
            p = str(output_stem) + ".json"
            gen.to_json(report, p); written.append(p)

    for p in written:
        console.print(f"[bold green]OK[/bold green] Report saved -> [cyan]{p}[/cyan]")

    return report


def _print_summary(report: dict, con: Console):
    score = report["health_score"]
    label = report["health_label"]
    m = report["metrics"]
    patterns = report["patterns"].get("clusters", [])
    rcs = report["root_causes"].get("root_causes", [])
    recs = report["recommendations"]

    color = {"Healthy": "green", "Fair": "yellow", "At Risk": "red", "Critical": "bold red"}.get(label, "white")

    con.print()
    con.print(Panel(
        f"[{color}]Health Score: {score}/100 — {label}[/{color}]\n"
        f"Total: {m['total']}  |  Open: {m['open']}  |  P1 Open: {m['p1_open']}  |  "
        f"Patterns: {len(patterns)}  |  Root Causes: {len(rcs)}",
        title="[bold]Ops Health Report[/bold]",
        border_style=color,
    ))

    if patterns:
        tbl = Table("Cluster", "Tickets", "Trend", "Recurrence", "Keywords", box=box.SIMPLE_HEAVY, header_style="bold cyan")
        for pat in patterns[:5]:
            tbl.add_row(
                pat["label"][:40],
                str(pat["size"]),
                pat["trend"],
                pat["recurrence"],
                ", ".join(pat["keywords"][:3]),
            )
        con.print("\n[bold]Top Recurring Patterns[/bold]")
        con.print(tbl)

    if recs:
        rec_tbl = Table("Pri", "Finding", "Action", box=box.SIMPLE, header_style="bold yellow")
        for rec in recs[:5]:
            pri_color = {"High": "red", "Medium": "yellow", "Low": "cyan"}.get(rec["priority"], "white")
            rec_tbl.add_row(
                f"[{pri_color}]{rec['priority']}[/{pri_color}]",
                rec["finding"][:55],
                rec["action"][:65],
            )
        con.print("\n[bold]Top Recommendations[/bold]")
        con.print(rec_tbl)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """ServiceNow Ops Analyzer — classify, cluster, and report on ticket data."""


# ------------------------------------------------------------------ analyze

@cli.command()
@click.argument("input_path", metavar="INPUT")
@click.option("--output", "-o", default="ops_health_report",
              help="Output file stem (no extension). Default: ops_health_report")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["html", "md", "text", "json", "all"], case_sensitive=False),
              default="all", show_default=True,
              help="Output format(s).")
@click.option("--quiet", "-q", is_flag=True, help="Suppress terminal summary.")
@click.option("--encoding", default="utf-8", show_default=True,
              help="CSV file encoding.")
def analyze(input_path, output, fmt, quiet, encoding):
    """
    Analyze a local CSV or JSON export.

    INPUT can be a file path, directory (all *.csv), or glob pattern.

    Examples:

    \b
        snow-analyzer analyze incidents.csv
        snow-analyzer analyze exports/ --format html -o reports/ops
        snow-analyzer analyze "data/*.csv" --format all
    """
    loader = DataLoader()
    path = Path(input_path)
    try:
        if str(path).endswith(".json"):
            console.print(f"[bold]Loading JSON:[/bold] {input_path}")
            df = loader.load_json(path)
        else:
            console.print(f"[bold]Loading CSV:[/bold] {input_path}")
            df = loader.load_csv(path, encoding=encoding)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Failed to load data:[/bold red] {e}")
        sys.exit(1)

    if df.empty:
        console.print("[bold yellow]Warning:[/bold yellow] No records loaded. Check file path and format.")
        sys.exit(1)

    console.print(f"[green]Loaded {len(df)} tickets.[/green]")
    _run_pipeline(df, output, fmt, quiet)


# ------------------------------------------------------------------ fetch

@cli.command()
@click.option("--instance", "-i", required=True,
              help="ServiceNow instance URL, e.g. https://myco.service-now.com")
@click.option("--table", "-t", default="incident", show_default=True,
              help="Table to query: incident | change_request | problem")
@click.option("--days", "-d", default=30, show_default=True,
              help="Fetch tickets opened in the last N days.")
@click.option("--username", "-u", envvar="SNOW_USERNAME",
              help="ServiceNow username (or set SNOW_USERNAME env var).")
@click.option("--password", "-p", envvar="SNOW_PASSWORD",
              help="ServiceNow password (or set SNOW_PASSWORD env var).")
@click.option("--token", envvar="SNOW_TOKEN",
              help="Bearer token (or set SNOW_TOKEN env var).")
@click.option("--query", default=None,
              help="Extra sysparm_query filter, e.g. 'assignment_group=IT Ops'")
@click.option("--output", "-o", default="ops_health_report", show_default=True)
@click.option("--format", "-f", "fmt",
              type=click.Choice(["html", "md", "text", "json", "all"], case_sensitive=False),
              default="all", show_default=True)
@click.option("--quiet", "-q", is_flag=True)
@click.option("--save-raw", is_flag=True,
              help="Save raw fetched data to <output>_raw.csv before analysis.")
def fetch(instance, table, days, username, password, token, query, output, fmt, quiet, save_raw):
    """
    Pull live data from ServiceNow REST API and analyze.

    Credentials are read from flags or env vars (SNOW_USERNAME, SNOW_PASSWORD,
    SNOW_TOKEN). OAuth/Bearer token takes precedence over basic auth.

    Examples:

    \b
        snow-analyzer fetch --instance https://myco.service-now.com --days 14
        SNOW_TOKEN=xxx snow-analyzer fetch -i https://myco.service-now.com -t change_request
    """
    loader = DataLoader()
    console.print(f"[bold]Fetching {table} from {instance} (last {days} days)…[/bold]")
    try:
        df = loader.load_api(
            instance_url=instance,
            table=table,
            days=days,
            username=username,
            password=password,
            token=token,
            extra_filters=query,
        )
    except Exception as e:
        console.print(f"[bold red]API error:[/bold red] {e}")
        sys.exit(1)

    if df.empty:
        console.print("[yellow]No records returned from API.[/yellow]")
        sys.exit(0)

    console.print(f"[green]Fetched {len(df)} records.[/green]")

    if save_raw:
        raw_path = str(output) + "_raw.csv"
        df.to_csv(raw_path, index=False)
        console.print(f"[cyan]Raw data saved → {raw_path}[/cyan]")

    _run_pipeline(df, output, fmt, quiet, days_label=f"Last {days} days")


# ------------------------------------------------------------------ demo

@cli.command()
@click.option("--tickets", "-n", default=300, show_default=True,
              help="Number of synthetic tickets to generate.")
@click.option("--output", "-o", default="demo_report", show_default=True)
@click.option("--format", "-f", "fmt",
              type=click.Choice(["html", "md", "text", "json", "all"], case_sensitive=False),
              default="all", show_default=True)
@click.option("--seed", default=42, show_default=True, help="Random seed.")
def demo(tickets, output, fmt, seed):
    """
    Generate synthetic ServiceNow data and run a full demo analysis.

    Great for testing, previewing the report format, or onboarding.

    Example:

    \b
        snow-analyzer demo --tickets 500 --format html
    """
    from demo_data import generate_demo_dataframe
    console.print(f"[bold]Generating {tickets} synthetic tickets (seed={seed})…[/bold]")
    df = generate_demo_dataframe(n=tickets, seed=seed)
    loader = DataLoader()
    df = loader._normalize(df)
    console.print(f"[green]Generated {len(df)} tickets.[/green]")
    _run_pipeline(df, output, fmt, quiet=False)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
