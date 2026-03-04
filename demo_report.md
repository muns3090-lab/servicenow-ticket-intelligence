# Ops Health Report

**Generated:** 2026-02-27 06:05 UTC  
**Period:** 2025-11-28 → 2026-02-27  
**Health Score:** 9/100 — Critical

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Tickets | 300 |
| Open | 92 |
| P1 Open | 14 |
| Resolved | 208 |
| Recurring Patterns | 39 |
| Root Cause Clusters | 10 |
| Tickets w/o Root Cause | 55.3% |

> **Open Ticket Status:** 92 ticket(s) remain open. 14 are P1 (critical). 83 have been open for more than 7 days.

---

## Priority Breakdown & MTTR

| Priority | Count | Avg MTTR | SLA Breach |
|----------|-------|----------|------------|
| P1 | 49 | 3.7h | 28.6% |
| P2 | 77 | 7.3h | 38.6% |
| P3 | 148 | 10.6h | 13.4% |
| P4 | 26 | 40.0h | 12.5% |

---

## Recurring Patterns (39 clusters)

### 1. Users Locked / Users Issues

- **Tickets:** 20 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Multiple times per week
- **P1/P2/P3:** 2 / 9 / 8
- **First seen:** 2025-12-04 &nbsp; **Last seen:** 2026-02-24
- **Affected services:** Email & Messaging, Customer Portal, Data Warehouse
- **Teams:** Security Operations, Helpdesk, App Support
- **Keywords:** `users locked, users, multiple users, out, out active`

### 2. Database / Severely Issues

- **Tickets:** 16 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Multiple times per week
- **P1/P2/P3:** 5 / 6 / 3
- **First seen:** 2025-12-09 &nbsp; **Last seen:** 2026-02-21
- **Affected services:** Data Warehouse, ERP System, Finance System
- **Teams:** Database Team, Network Operations, Helpdesk
- **Keywords:** `database, severely, performance, performance severely, query`

### 3. Reported / Vpn Disconnections Issues

- **Tickets:** 16 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Multiple times per week
- **P1/P2/P3:** 5 / 4 / 7
- **First seen:** 2025-11-28 &nbsp; **Last seen:** 2026-02-02
- **Affected services:** ERP System, CI/CD Pipeline, Customer Portal
- **Teams:** Helpdesk, App Support, Database Team
- **Keywords:** `reported, vpn disconnections, vpn, reported across, intermittent`

### 4. Database / Slow Issues

- **Tickets:** 15 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Multiple times per week
- **P1/P2/P3:** 3 / 4 / 4
- **First seen:** 2025-11-30 &nbsp; **Last seen:** 2026-02-13
- **Affected services:** Data Warehouse, Email & Messaging, VPN Gateway
- **Teams:** Identity & Access, Database Team, DevOps
- **Keywords:** `database, slow, query alerts, slow query, production`

### 5. Utilization 98 / Utilization Issues

- **Tickets:** 14 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Multiple times per week
- **P1/P2/P3:** 2 / 7 / 5
- **First seen:** 2025-12-12 &nbsp; **Last seen:** 2026-02-22
- **Affected services:** HR Platform, Data Warehouse, CI/CD Pipeline
- **Teams:** Database Team, Network Operations, App Support
- **Keywords:** `utilization 98, utilization, server disk, server, application`

### 6. Backup / Space Issues

- **Tickets:** 13 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Multiple times per week
- **P1/P2/P3:** 2 / 4 / 6
- **First seen:** 2025-11-30 &nbsp; **Last seen:** 2026-02-16
- **Affected services:** VPN Gateway, HR Platform, Finance System
- **Teams:** Database Team, DevOps, Security Operations
- **Keywords:** `backup, space, disk space, database, insufficient disk`

### 7. Vpn Connectivity / Vpn Issues

- **Tickets:** 12 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Multiple times per week
- **P1/P2/P3:** 3 / 4 / 4
- **First seen:** 2025-11-29 &nbsp; **Last seen:** 2026-02-25
- **Affected services:** Finance System, API Gateway, VPN Gateway
- **Teams:** Cloud Operations, Infrastructure, Helpdesk
- **Keywords:** `vpn connectivity, vpn, remote, dropped, connectivity dropped`

### 8. Users Unable / Users Issues

- **Tickets:** 12 &nbsp; **Trend:** Stable &nbsp; **Recurrence:** Weekly
- **P1/P2/P3:** 2 / 4 / 3
- **First seen:** 2025-11-29 &nbsp; **Last seen:** 2026-02-15
- **Affected services:** Core Network, CI/CD Pipeline, API Gateway
- **Teams:** DevOps, Infrastructure, Cloud Operations
- **Keywords:** `users unable, users, unable send, smtp relay, unable`

---

## Root Cause Clusters

### 1. Successfully / Completed Successfully

- **Tickets:** 60
- **Keywords:** `successfully, completed successfully, completed`
- **Recommendations:**
  - Add disk utilization alerts at 80 % / 90 % thresholds and schedule automated cleanup jobs.

### 2. Firewall / Updated

- **Tickets:** 41
- **Keywords:** `firewall, updated, firewall rule, rule, updated firewall`
- **Recommendations:**
  - Review firewall rule changes, implement network topology documentation, and set up synthetic monitoring.
  - Enforce canary/blue-green deployments and automated rollback triggers for failed health checks.

### 3. Leak / Vpn

- **Tickets:** 22
- **Keywords:** `leak, vpn, gateway, memory leak, memory`
- **Recommendations:**
  - Profile the application for memory leaks, tune JVM/container memory limits, and set OOM alerts.
  - Review firewall rule changes, implement network topology documentation, and set up synthetic monitoring.

### 4. System / Hr

- **Tickets:** 17
- **Keywords:** `system, hr, hr system, reset, reset accounts`
- **Recommendations:**
  - Implement self-service password reset and proactive account expiry notifications.

### 5. Log / Log Rotation

- **Tickets:** 14
- **Keywords:** `log, log rotation, rotation, rotation frequency, old`

### 6. Load / Load Balancer

- **Tickets:** 13
- **Keywords:** `load, load balancer, balancer, certificate, url`
- **Recommendations:**
  - Set up automated certificate expiry monitoring with alerts at 30/14/7 days before expiry.

---

## Actionable Recommendations

| # | Priority | Finding | Action |
|---|----------|---------|--------|
| 1 | **High** | P1 SLA breached 28.6% of the time | Review P1 escalation path, on-call coverage, and runbook completeness. |
| 2 | **High** | 14 P1 ticket(s) currently open | Escalate open P1 incidents immediately; conduct a bridge call if multiple services affected. |
| 3 | **Medium** | Recurring pattern: 'Users Locked / Users Issues' (20 tickets, trend: Stable) | Open a Problem ticket to address root cause. Top keywords: users locked, users, multiple users. Primarily affects: Email & Messaging, Customer Portal. |
| 4 | **Medium** | Recurring pattern: 'Database / Severely Issues' (16 tickets, trend: Stable) | Open a Problem ticket to address root cause. Top keywords: database, severely, performance. Primarily affects: Data Warehouse, ERP System. |
| 5 | **Medium** | Recurring pattern: 'Reported / Vpn Disconnections Issues' (16 tickets, trend: Stable) | Open a Problem ticket to address root cause. Top keywords: reported, vpn disconnections, vpn. Primarily affects: ERP System, CI/CD Pipeline. |
| 6 | **Medium** | Root cause cluster: 'Successfully / Completed Successfully' (60 tickets) | Add disk utilization alerts at 80 % / 90 % thresholds and schedule automated cleanup jobs. |
| 7 | **Medium** | Root cause cluster: 'Firewall / Updated' (41 tickets) | Review firewall rule changes, implement network topology documentation, and set up synthetic monitoring. |
| 8 | **Medium** | Root cause cluster: 'Firewall / Updated' (41 tickets) | Enforce canary/blue-green deployments and automated rollback triggers for failed health checks. |
| 9 | **Medium** | Root cause cluster: 'Leak / Vpn' (22 tickets) | Profile the application for memory leaks, tune JVM/container memory limits, and set OOM alerts. |
| 10 | **Low** | 55.3% of resolved tickets have no root cause recorded | Enforce root cause capture in closure workflow; add mandatory field to ticket resolution form. |

---

*ServiceNow Ops Analyzer — 2026-02-27 06:05 UTC*