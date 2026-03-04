"""
Synthetic ServiceNow data generator for demo/testing purposes.

Produces realistic-looking incident and change data with:
- Multiple recurring issue clusters (VPN outages, DB slow queries, etc.)
- Mixed priorities, states, categories
- MTTR variation by priority
- Partially filled root_cause / close_notes
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Templates: (weight, short_description, category, resolution_note, cause)
# ---------------------------------------------------------------------------

INCIDENT_TEMPLATES = [
    # Network / VPN cluster
    (8, "VPN connectivity dropped for remote users",
     "Network", "Restarted VPN concentrator and updated firewall rules",
     "Firewall rule expired after policy rotation"),
    (6, "Users unable to connect to VPN from home network",
     "Network", "Updated split-tunnel configuration and cleared routing table",
     "VPN routing config overwritten during maintenance window"),
    (5, "Intermittent VPN disconnections reported across APAC region",
     "Network", "Upgraded VPN gateway firmware to resolve memory leak",
     "Memory leak in VPN gateway firmware v3.2.1"),
    (4, "Network latency spike causing application timeouts",
     "Network", "Identified BGP route flapping; stabilised routing",
     "BGP peer de-peered due to ISP maintenance"),
    (3, "DNS resolution failures for internal domains",
     "Network", "Flushed DNS cache on primary resolver and fixed zone record",
     "Stale DNS zone cache after domain migration"),
    # Database cluster
    (7, "Database query performance severely degraded",
     "Database", "Rebuilt missing index on orders table; query time reduced from 45s to 0.3s",
     "Index dropped accidentally during schema migration"),
    (6, "Slow query alerts firing on production database",
     "Database", "Identified runaway reporting query, added query timeout and index",
     "Ad-hoc reporting query without index caused full table scan"),
    (4, "Database connection pool exhausted",
     "Database", "Increased connection pool size and found connection leak in app",
     "Connection leak in ORM layer not properly closing sessions"),
    (3, "Oracle deadlock errors in application logs",
     "Database", "Reviewed lock ordering in stored procedures, fixed transaction order",
     "Inconsistent lock acquisition order between two concurrent transactions"),
    # SSL / Certificate cluster
    (6, "HTTPS certificate expired causing browser warnings",
     "Application", "Renewed SSL certificate and deployed to load balancer",
     "Certificate expiry not tracked; monitoring gap"),
    (5, "API gateway returning SSL handshake failures",
     "Application", "Replaced expired wildcard certificate on API gateway cluster",
     "Wildcard certificate expired; auto-renewal misconfigured"),
    (4, "Internal service-to-service TLS errors after certificate rotation",
     "Security", "Re-distributed new CA bundle to all microservices",
     "CA bundle not propagated after certificate authority rotation"),
    # Disk / Storage cluster
    (6, "Application server disk utilization at 98%",
     "Infrastructure", "Removed old log files and increased log rotation frequency",
     "Log rotation policy misconfigured; logs not purged for 60 days"),
    (5, "Database backup failed due to insufficient disk space",
     "Storage & Backup", "Extended volume size and cleared orphaned backup files",
     "Backup volume not sized for growing dataset"),
    (3, "File upload service returning 507 Insufficient Storage",
     "Application", "Provisioned additional NAS storage and updated quota policy",
     "Storage quota set too conservatively for peak usage"),
    # Access / Auth cluster
    (7, "Multiple users locked out of Active Directory accounts",
     "Access & Identity", "Reset accounts and identified sync issue with HR system",
     "HR system de-provisioning job running with wrong OU filter"),
    (5, "SSO service returning 403 for application after config change",
     "Access & Identity", "Rolled back SSO application config to previous version",
     "Incorrect SAML assertion attribute mapping after IdP upgrade"),
    (4, "Password reset self-service portal returning 500 error",
     "Access & Identity", "Fixed broken redirect URL after load balancer update",
     "Load balancer SSL termination changed callback URL scheme"),
    # Performance cluster
    (5, "Application response time exceeding 10 seconds",
     "Performance", "Enabled query caching and optimised N+1 query patterns",
     "Recent feature deployment introduced N+1 database query pattern"),
    (4, "Memory usage on API servers at 95%, OOM kill events observed",
     "Infrastructure", "Increased heap size and fixed memory leak in session handler",
     "Session objects not garbage collected due to circular reference"),
    (3, "CPU saturation on worker nodes causing job queue backlog",
     "Performance", "Added two worker nodes and optimised job batch sizes",
     "Black Friday traffic spike exceeded provisioned capacity"),
    # Deployment / Change cluster
    (5, "Production deployment caused 15-minute service outage",
     "Application", "Rolled back deployment; identified missing DB migration",
     "Schema migration not run before application deployment"),
    (4, "Configuration change pushed to wrong environment",
     "Infrastructure", "Reverted config change and added environment tagging validation",
     "Manual config push targeted prod instead of staging"),
    (3, "Kubernetes pod crash loop after image update",
     "Application", "Rolled back to previous container image; fixed environment variable",
     "Missing environment variable in new container image build"),
    # Monitoring / Alert
    (3, "PagerDuty alert storm due to misconfigured threshold",
     "Monitoring & Alerting", "Updated alert threshold from 80% to 90% CPU after review",
     "Alert threshold set too aggressively during initial setup"),
    (2, "Grafana dashboards returning no data after Prometheus restart",
     "Monitoring & Alerting", "Re-enabled remote write and fixed Prometheus retention config",
     "Prometheus retention config wiped after upgrade"),
    # Email
    (3, "Users unable to send emails; SMTP relay rejecting connections",
     "Email & Communication", "Updated firewall rule to allow SMTP from new server subnet",
     "Firewall rule not updated after email server migration"),
    (2, "Outlook calendar sync failing for mobile devices",
     "Email & Communication", "Re-enrolled devices in MDM and reset Exchange ActiveSync",
     "MDM certificate expired causing EAS connection rejection"),
]

CHANGE_TEMPLATES = [
    ("Upgrade database to version 14.2",          "Database",       "Normal"),
    ("Deploy application release v2.5.0",         "Application",    "Normal"),
    ("Firewall rule update for new server subnet", "Network",        "Normal"),
    ("Patch operating system CVE-2024-1234",       "Security",       "Normal"),
    ("Expand NAS storage volume by 2TB",           "Infrastructure", "Normal"),
    ("Rotate API keys for third-party integrations","Security",      "Normal"),
    ("DNS migration to new resolver cluster",      "Network",        "Normal"),
    ("Enable MFA for all admin accounts",          "Security",       "Standard"),
    ("Quarterly certificate renewal",             "Security",       "Standard"),
    ("Emergency rollback of auth service",        "Application",    "Emergency"),
    ("Emergency firewall rule for DDoS mitigation","Network",       "Emergency"),
]

GROUPS = [
    "Network Operations", "Database Team", "App Support",
    "Infrastructure", "Security Operations", "Identity & Access",
    "Cloud Operations", "DevOps", "Helpdesk",
]

SERVICES = [
    "ERP System", "Customer Portal", "Email & Messaging", "VPN Gateway",
    "HR Platform", "Finance System", "Data Warehouse", "CI/CD Pipeline",
    "API Gateway", "Core Network",
]

CIS = [
    "prod-db-01", "vpn-gw-01", "app-server-cluster", "nas-01",
    "auth-service", "api-gateway", "web-lb-01", "k8s-worker-pool",
    "smtp-relay", "dns-resolver",
]

PRIORITIES = ["P1", "P1", "P2", "P2", "P2", "P3", "P3", "P3", "P3", "P4"]
STATES_RESOLVED = ["Resolved", "Closed"]
STATES_OPEN = ["New", "In Progress", "On Hold"]


def generate_demo_dataframe(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    n_incidents = int(n * 0.80)
    n_changes = n - n_incidents

    now = datetime.now(timezone.utc)
    records = []

    # --- Incidents ---
    weights = [t[0] for t in INCIDENT_TEMPLATES]
    total_w = sum(weights)
    probs = [w / total_w for w in weights]

    for i in range(n_incidents):
        tmpl_idx = rng.choices(range(len(INCIDENT_TEMPLATES)), weights=probs)[0]
        _, short_desc, category, resolution, cause = INCIDENT_TEMPLATES[tmpl_idx]

        # Add slight variation to descriptions
        variations = [
            short_desc,
            short_desc.replace("users", "staff").replace("user", "employee"),
            short_desc + " - escalated by helpdesk",
            short_desc + " (reported via monitoring)",
            "URGENT: " + short_desc,
        ]
        short_desc_v = rng.choice(variations)

        opened_at = now - timedelta(
            days=rng.randint(0, 90),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )

        priority = rng.choice(PRIORITIES)
        mttr_base = {"P1": 3, "P2": 7, "P3": 20, "P4": 50}.get(priority, 24)
        mttr_hours = max(0.25, np_rng.exponential(mttr_base))

        # 30% chance open
        is_open = rng.random() < 0.30
        if is_open:
            state = rng.choice(STATES_OPEN)
            resolved_at = pd.NaT
        else:
            state = rng.choice(STATES_RESOLVED)
            resolved_at = opened_at + timedelta(hours=mttr_hours)

        # 60% chance has root cause
        has_rc = rng.random() < 0.60
        # 70% chance has close notes
        has_notes = rng.random() < 0.70

        records.append({
            "number": f"INC{100000 + i:06d}",
            "short_description": short_desc_v,
            "description": f"Details: {short_desc_v}. Category: {category}.",
            "category": category,
            "subcategory": "",
            "priority": priority,
            "state": state,
            "assigned_to": rng.choice(["alice.smith", "bob.jones", "carol.wu", "dave.patel", "eve.kim"]),
            "assignment_group": rng.choice(GROUPS),
            "opened_at": opened_at,
            "resolved_at": resolved_at,
            "closed_at": resolved_at if not is_open else pd.NaT,
            "cmdb_ci": rng.choice(CIS),
            "business_service": rng.choice(SERVICES),
            "close_notes": resolution if has_notes and not is_open else "",
            "root_cause": cause if has_rc and not is_open else "",
            "record_type": "Incident",
            "type": "",
            "caller": f"user{rng.randint(1, 200)}@example.com",
        })

    # --- Changes ---
    for i in range(n_changes):
        tmpl = rng.choice(CHANGE_TEMPLATES)
        short_desc, category, chg_type = tmpl
        opened_at = now - timedelta(days=rng.randint(0, 90), hours=rng.randint(0, 23))
        resolved_at = opened_at + timedelta(hours=rng.randint(1, 8))
        records.append({
            "number": f"CHG{200000 + i:06d}",
            "short_description": short_desc,
            "description": f"Change: {short_desc}",
            "category": category,
            "subcategory": "",
            "priority": "P3",
            "state": rng.choice(["Closed", "Closed", "In Progress"]),
            "assigned_to": rng.choice(["alice.smith", "bob.jones", "carol.wu"]),
            "assignment_group": rng.choice(GROUPS),
            "opened_at": opened_at,
            "resolved_at": resolved_at,
            "closed_at": resolved_at,
            "cmdb_ci": rng.choice(CIS),
            "business_service": rng.choice(SERVICES),
            "close_notes": "Change completed successfully.",
            "root_cause": "",
            "record_type": "Change",
            "type": chg_type,
            "caller": f"user{rng.randint(1, 200)}@example.com",
        })

    df = pd.DataFrame(records)
    return df
