"""
Root cause analysis: cluster resolution notes / close_notes to surface
recurring fix patterns, and recommend preventive actions.

Pipeline:
  1. Use close_notes + root_cause fields (resolution text).
  2. TF-IDF + KMeans (k chosen by silhouette score).
  3. Label each root cause cluster with top keywords.
  4. Link back to pattern clusters and generate recommendations.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from config import KMEANS_MAX_CLUSTERS, TFIDF_MAX_FEATURES
from analysis.patterns import _clean, _top_keywords, STOP_WORDS


# ---------------------------------------------------------------------------
# Recommendation templates keyed on root cause keywords
# ---------------------------------------------------------------------------
RECOMMENDATION_TEMPLATES: list[tuple[list[str], str]] = [
    (
        ["certificate", "ssl", "tls", "expired", "expir"],
        "Set up automated certificate expiry monitoring with alerts at 30/14/7 days before expiry.",
    ),
    (
        ["password", "unlock", "account", "locked", "expire"],
        "Implement self-service password reset and proactive account expiry notifications.",
    ),
    (
        ["disk", "space", "full", "quota", "storage"],
        "Add disk utilization alerts at 80 % / 90 % thresholds and schedule automated cleanup jobs.",
    ),
    (
        ["memory", "oom", "out of memory", "heap", "leak"],
        "Profile the application for memory leaks, tune JVM/container memory limits, and set OOM alerts.",
    ),
    (
        ["cpu", "high cpu", "utilization", "overload"],
        "Establish CPU utilization baselines, configure auto-scaling policies, and review resource-intensive jobs.",
    ),
    (
        ["network", "connectivity", "vpn", "firewall"],
        "Review firewall rule changes, implement network topology documentation, and set up synthetic monitoring.",
    ),
    (
        ["deploy", "release", "rollback", "update", "patch"],
        "Enforce canary/blue-green deployments and automated rollback triggers for failed health checks.",
    ),
    (
        ["reboot", "restart", "crash", "hang", "freeze"],
        "Investigate crash dumps, add watchdog timers, and establish a post-incident review process.",
    ),
    (
        ["backup", "restore", "recovery"],
        "Test backup restoration monthly, document RTO/RPO targets, and automate backup validation.",
    ),
    (
        ["timeout", "slow", "performance", "response"],
        "Add APM tracing, review slow query logs, and set SLA-based alerting on response times.",
    ),
    (
        ["permission", "access", "forbidden", "403", "unauthorized"],
        "Audit access control lists quarterly, automate provisioning/de-provisioning via ITSM workflows.",
    ),
    (
        ["config", "configuration", "misconfiguration", "wrong setting"],
        "Introduce configuration-as-code and drift detection to catch unauthorised changes automatically.",
    ),
]


def _map_recommendations(keywords: list[str]) -> list[str]:
    """Map cluster keywords to recommendation strings."""
    lower_kws = {k.lower() for k in keywords}
    recs = []
    for trigger_kws, rec in RECOMMENDATION_TEMPLATES:
        if any(t in lower_kws or any(t in kw for kw in lower_kws) for t in trigger_kws):
            recs.append(rec)
    return recs[:3]  # cap at 3


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class RootCauseAnalyzer:
    """Cluster resolution notes to surface recurring root causes."""

    def __init__(self, max_clusters: int = KMEANS_MAX_CLUSTERS):
        self.max_clusters = max_clusters

    # ------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        pattern_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze root causes from resolution text.

        Returns:
          {
            "root_causes": [...],
            "unresolved_insight": str,
            "top_repeated_actions": [...],
          }
        """
        # Build resolution corpus: combine root_cause + close_notes
        df = df.copy()
        df["resolution_text"] = (
            df["root_cause"].fillna("") + " " + df["close_notes"].fillna("")
        ).str.strip()

        # Only analyze tickets that have resolution text
        resolved = df[df["resolution_text"].str.len() > 10].copy()

        if len(resolved) < 5:
            return {
                "root_causes": [],
                "unresolved_insight": self._unresolved_insight(df),
                "top_repeated_actions": [],
            }

        texts = resolved["resolution_text"].fillna("").tolist()
        cleaned = [_clean(t) for t in texts]

        # TF-IDF
        vec = TfidfVectorizer(
            max_features=min(TFIDF_MAX_FEATURES, 800),
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
            stop_words=list(STOP_WORDS),
        )
        try:
            X = vec.fit_transform(cleaned)
        except ValueError:
            return {
                "root_causes": [],
                "unresolved_insight": self._unresolved_insight(df),
                "top_repeated_actions": [],
            }

        # Choose k via silhouette score
        n_samples = X.shape[0]
        max_k = min(self.max_clusters, n_samples - 1, 10)
        best_k = 3
        best_score = -1.0

        if n_samples >= 6:
            for k in range(2, max_k + 1):
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels_tmp = km.fit_predict(X)
                if len(set(labels_tmp)) < 2:
                    continue
                try:
                    score = silhouette_score(X, labels_tmp, metric="cosine", sample_size=min(300, n_samples))
                    if score > best_score:
                        best_score = score
                        best_k = k
                except Exception:
                    pass
        else:
            best_k = 2

        km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        cluster_labels = km_final.fit_predict(X)
        resolved = resolved.copy()
        resolved["rc_cluster"] = cluster_labels

        root_causes = []
        for cid in range(best_k):
            mask = cluster_labels == cid
            cluster_rows = resolved[mask]
            if cluster_rows.empty:
                continue

            rc_texts = cluster_rows["resolution_text"].tolist()
            keywords = _top_keywords(rc_texts, n=6)
            label = self._label_rc(keywords)
            recommendations = _map_recommendations(keywords)

            # Link to pattern clusters
            linked_patterns = []
            if pattern_result:
                for pat in pattern_result.get("clusters", []):
                    overlap = set(pat["ticket_numbers"]) & set(cluster_rows["number"].tolist())
                    if overlap:
                        linked_patterns.append(
                            {"pattern_id": pat["id"], "pattern_label": pat["label"], "shared_tickets": len(overlap)}
                        )

            priority_dist = (
                cluster_rows["priority"]
                .value_counts()
                .reindex(["P1", "P2", "P3", "P4", "Unknown"], fill_value=0)
                .to_dict()
            )

            groups = [g for g in cluster_rows["assignment_group"].dropna() if g]
            top_groups = [g for g, _ in Counter(groups).most_common(2)]

            avg_mttr = (
                cluster_rows["mttr_hours"].dropna().mean()
                if "mttr_hours" in cluster_rows.columns
                else None
            )

            root_causes.append(
                {
                    "id": int(cid),
                    "label": label,
                    "keywords": keywords,
                    "ticket_count": int(len(cluster_rows)),
                    "priority_dist": priority_dist,
                    "top_groups": top_groups,
                    "avg_mttr_hours": round(avg_mttr, 1) if avg_mttr else None,
                    "linked_patterns": linked_patterns,
                    "recommendations": recommendations,
                    "sample_resolutions": rc_texts[:3],
                }
            )

        # Sort by ticket_count
        root_causes.sort(key=lambda r: r["ticket_count"], reverse=True)

        return {
            "root_causes": root_causes,
            "unresolved_insight": self._unresolved_insight(df),
            "top_repeated_actions": self._top_repeated_actions(resolved),
        }

    # ------------------------------------------------------------------

    @staticmethod
    def _label_rc(keywords: list[str]) -> str:
        if not keywords:
            return "Unknown Root Cause"
        k = keywords[0].title()
        if len(keywords) > 1:
            return f"{k} / {keywords[1].title()}"
        return k

    @staticmethod
    def _unresolved_insight(df: pd.DataFrame) -> str:
        open_states = {"New", "In Progress", "On Hold"}
        open_tickets = df[df["state"].isin(open_states)]
        if open_tickets.empty:
            return "No currently open tickets detected."
        total = len(open_tickets)
        p1_open = int((open_tickets["priority"] == "P1").sum())
        aged = int((open_tickets["age_hours"] > 168).sum()) if "age_hours" in open_tickets.columns else 0
        parts = [f"{total} ticket(s) remain open."]
        if p1_open:
            parts.append(f"{p1_open} are P1 (critical).")
        if aged:
            parts.append(f"{aged} have been open for more than 7 days.")
        return " ".join(parts)

    @staticmethod
    def _top_repeated_actions(resolved: pd.DataFrame) -> list[str]:
        """Extract most common short resolution phrases."""
        all_text = " ".join(resolved["resolution_text"].tolist()).lower()
        # Simple n-gram frequency on non-stop-word bigrams
        words = re.findall(r"\b[a-z]{3,}\b", all_text)
        words = [w for w in words if w not in STOP_WORDS]
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        counts = Counter(bigrams)
        return [phrase for phrase, _ in counts.most_common(5)]
