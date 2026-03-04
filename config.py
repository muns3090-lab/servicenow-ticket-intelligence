"""
Central configuration: field mappings, keyword taxonomy, scoring weights.
"""

# ---------------------------------------------------------------------------
# ServiceNow column aliases → normalized column names
# Covers common export variants (Display vs Internal value columns).
# ---------------------------------------------------------------------------
COLUMN_ALIASES: dict[str, str] = {
    # Ticket identifier
    "number": "number",
    "incident_number": "number",
    "change_number": "number",
    # Descriptions
    "short_description": "short_description",
    "short description": "short_description",
    "title": "short_description",
    "description": "description",
    "comments_and_work_notes": "description",
    "work_notes": "description",
    # Classification
    "category": "category",
    "subcategory": "subcategory",
    "sub_category": "subcategory",
    # Priority / severity
    "priority": "priority",
    "severity": "priority",
    "impact": "impact",
    "urgency": "urgency",
    # State
    "state": "state",
    "incident_state": "state",
    "status": "state",
    # Assignment
    "assigned_to": "assigned_to",
    "assigned to": "assigned_to",
    "assignment_group": "assignment_group",
    "assignment group": "assignment_group",
    # Dates
    "opened_at": "opened_at",
    "created": "opened_at",
    "sys_created_on": "opened_at",
    "resolved_at": "resolved_at",
    "closed_at": "closed_at",
    "closed": "closed_at",
    # Configuration Item / Service
    "cmdb_ci": "cmdb_ci",
    "configuration_item": "cmdb_ci",
    "business_service": "business_service",
    "service_offering": "business_service",
    "affected_service": "business_service",
    # Resolution
    "close_notes": "close_notes",
    "resolution_notes": "close_notes",
    "u_root_cause": "root_cause",
    "root_cause": "root_cause",
    "cause": "root_cause",
    # Record type
    "sys_class_name": "record_type",
    "type": "type",
    "change_type": "type",
    # Caller / Reporter
    "caller_id": "caller",
    "reported_by": "caller",
    "opened_by": "caller",
}

# ---------------------------------------------------------------------------
# Priority normalization  →  canonical P1-P4 (+ Unknown)
# ---------------------------------------------------------------------------
PRIORITY_MAP: dict[str, str] = {
    # Numeric strings
    "1": "P1", "2": "P2", "3": "P3", "4": "P4", "5": "P5",
    # Labeled numbers
    "1 - critical": "P1", "2 - high": "P2", "3 - moderate": "P3",
    "4 - low": "P4", "5 - planning": "P5",
    # Words
    "critical": "P1", "emergency": "P1",
    "high": "P2",
    "medium": "P3", "moderate": "P3", "normal": "P3",
    "low": "P4",
    "planning": "P5", "informational": "P5",
    # Common service-desk variants
    "p1": "P1", "p2": "P2", "p3": "P3", "p4": "P4", "p5": "P5",
    "sev1": "P1", "sev2": "P2", "sev3": "P3", "sev4": "P4",
    "severity 1": "P1", "severity 2": "P2",
    "severity 3": "P3", "severity 4": "P4",
}

# ---------------------------------------------------------------------------
# State normalization  →  canonical buckets
# ---------------------------------------------------------------------------
STATE_MAP: dict[str, str] = {
    "1": "New", "new": "New",
    "2": "In Progress", "in progress": "In Progress",
    "work in progress": "In Progress", "wip": "In Progress",
    "3": "On Hold", "on hold": "On Hold", "pending": "On Hold",
    "awaiting vendor": "On Hold", "awaiting user": "On Hold",
    "4": "Resolved", "resolved": "Resolved",
    "5": "Closed", "closed": "Closed",
    "6": "Cancelled", "cancelled": "Cancelled", "canceled": "Cancelled",
}

# ---------------------------------------------------------------------------
# Category keyword taxonomy used for rule-based classification
# Order matters: first match wins for single-label classification.
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Network": [
        "network", "connectivity", "vpn", "firewall", "dns", "ping",
        "latency", "bandwidth", "switch", "router", "wifi", "wireless",
        "ethernet", "packet loss", "tcp", "ip address", "vlan", "wan",
        "lan", "proxy", "load balancer", "cdn", "routing",
    ],
    "Database": [
        "database", " db ", "sql", "oracle", "mysql", "postgres",
        "postgresql", "mongodb", "redis", "cassandra", "query",
        "table", "schema", "deadlock", "replication", "backup db",
        "restore", "index", "stored procedure", "transaction",
    ],
    "Application": [
        "application", " app ", "software", "crash", "error 5", "500",
        "exception", "bug", "deploy", "release", "build", "code",
        "api error", "service unavailable", "502", "503", "404",
        "frontend", "backend", "microservice", "container", "pod",
    ],
    "Infrastructure": [
        "server", "vm", "virtual machine", "storage", "disk", "memory",
        "cpu", "hardware", "datacenter", "data center", "cloud",
        "aws", "azure", "gcp", "kubernetes", "docker", "hypervisor",
        "vmware", "esxi", "san", "nas", "raid", "reboot", "restart",
    ],
    "Security": [
        "security", "vulnerability", "breach", "certificate", "ssl",
        "tls", "malware", "phishing", "ransomware", "intrusion",
        "firewall rule", "threat", "patch", "cve", "exploit",
        "compliance", "audit", "soc", "pen test", "encryption",
    ],
    "Access & Identity": [
        "access", "permission", "login", "authentication", "account",
        "password reset", "unlock", "provision", "sso", "saml",
        "oauth", "mfa", "2fa", "active directory", "ldap", "okta",
        "role", "entitlement", "privilege", "forbidden", "403",
    ],
    "Performance": [
        "slow", "performance", "timeout", "response time", "throughput",
        "bottleneck", "degraded", "high cpu", "high memory", "lag",
        "latency", "saturation", "resource contention", "overload",
    ],
    "Email & Communication": [
        "email", "outlook", "exchange", "teams", "slack", "zoom",
        "mailbox", "smtp", "imap", "calendar", "meeting", "voip",
        "phone", "conference", "notification",
    ],
    "Storage & Backup": [
        "backup", "restore", "snapshot", "archive", "disk full",
        "storage", "san", "nas", "file system", "quota", "replication",
    ],
    "Monitoring & Alerting": [
        "alert", "monitor", "alarm", "nagios", "grafana", "prometheus",
        "splunk", "dynatrace", "datadog", "pagerduty", "threshold",
        "health check", "dashboard",
    ],
}

# ---------------------------------------------------------------------------
# Scoring weights for the Ops Health Score (0–100)
# Deductions are capped per category to avoid runaway negatives.
# ---------------------------------------------------------------------------
HEALTH_SCORE_WEIGHTS = {
    "p1_open_per_ticket":      5.0,   # deducted per P1 open ticket (capped 30)
    "p1_breach_per_ticket":    3.0,   # P1 with MTTR > 4h (capped 20)
    "recurring_pattern":       4.0,   # per detected recurring cluster (capped 20)
    "unresolved_7d":           2.0,   # per ticket open > 7 days (capped 15)
    "high_volume_increase":    5.0,   # per 20 % volume increase vs prior period
    "no_root_cause_rate":      0.1,   # per % of tickets with no root cause (capped 10)
}

# MTTR SLA targets (hours) per priority
MTTR_SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}

# Minimum cluster size for a pattern to be considered "recurring"
MIN_CLUSTER_SIZE = 3

# DBSCAN / KMeans parameters
DBSCAN_EPS = 0.35
DBSCAN_MIN_SAMPLES = 3
KMEANS_MAX_CLUSTERS = 12
TFIDF_MAX_FEATURES = 1500

# ServiceNow REST API defaults
SNOW_API_PAGE_SIZE = 1000
SNOW_API_TIMEOUT = 30
