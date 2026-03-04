"""
Pattern detection: find recurring clusters of similar tickets.

Pipeline:
  1. TF-IDF vectorize full_text.
  2. DBSCAN clustering (density-based, no need to choose k).
  3. Label each cluster with its top keywords.
  4. Enrich each cluster with metadata (priority dist, affected services,
     assignment groups, trend, recurrence estimate).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import (
    DBSCAN_EPS,
    DBSCAN_MIN_SAMPLES,
    MIN_CLUSTER_SIZE,
    TFIDF_MAX_FEATURES,
)


# ---------------------------------------------------------------------------
# Stop words to exclude from cluster labels
# ---------------------------------------------------------------------------
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "not", "no", "nor",
    "so", "yet", "both", "either", "neither", "each", "few", "more", "most",
    "other", "such", "than", "too", "very", "just", "due", "via", "per",
    "ticket", "incident", "change", "user", "issue", "problem", "request",
    "please", "need", "want", "get", "set", "update", "new", "hi", "hello",
}


def _clean(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _top_keywords(texts: list[str], n: int = 5) -> list[str]:
    """Extract top n keywords from a list of texts using TF-IDF."""
    if not texts:
        return []
    vec = TfidfVectorizer(
        max_features=200,
        ngram_range=(1, 2),
        stop_words=list(STOP_WORDS),
        min_df=1,
    )
    try:
        X = vec.fit_transform([_clean(t) for t in texts])
        scores = np.asarray(X.mean(axis=0)).flatten()
        top_idx = scores.argsort()[-n:][::-1]
        features = vec.get_feature_names_out()
        return [features[i] for i in top_idx if scores[i] > 0]
    except ValueError:
        return []


def _label_cluster(keywords: list[str]) -> str:
    """Turn a keyword list into a human-readable cluster label."""
    if not keywords:
        return "Uncategorized Issues"
    # Capitalize first keyword, list rest
    parts = [keywords[0].title()]
    if len(keywords) > 1:
        parts.append(f"/ {keywords[1].title()}")
    return " ".join(parts) + " Issues"


def _estimate_recurrence(dates: pd.Series) -> str:
    """Estimate recurrence frequency from a series of datetimes."""
    valid = dates.dropna().sort_values()
    if len(valid) < 2:
        return "Insufficient data"
    gaps = valid.diff().dropna().dt.total_seconds() / 3600  # in hours
    median_gap = gaps.median()
    if median_gap < 2:
        return "Continuous / ongoing"
    if median_gap < 24:
        return "Multiple times per day"
    if median_gap < 168:
        return "Multiple times per week"
    if median_gap < 720:
        return "Weekly"
    return "Monthly or less"


def _trend(df: pd.DataFrame) -> str:
    """Compare first half vs second half ticket volume."""
    if df["opened_at"].isna().all():
        return "Unknown"
    df_s = df.sort_values("opened_at")
    mid = len(df_s) // 2
    first_half = len(df_s.iloc[:mid])
    second_half = len(df_s.iloc[mid:])
    if second_half == 0:
        return "Unknown"
    ratio = second_half / max(first_half, 1)
    if ratio > 1.3:
        return "Increasing"
    if ratio < 0.7:
        return "Decreasing"
    return "Stable"


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class PatternDetector:
    """Detect recurring ticket patterns using DBSCAN clustering on TF-IDF."""

    def __init__(
        self,
        eps: float = DBSCAN_EPS,
        min_samples: int = DBSCAN_MIN_SAMPLES,
        min_cluster_size: int = MIN_CLUSTER_SIZE,
    ):
        self.eps = eps
        self.min_samples = min_samples
        self.min_cluster_size = min_cluster_size
        self._vectorizer: TfidfVectorizer | None = None

    # ------------------------------------------------------------------

    def detect(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Run pattern detection.

        Returns:
          {
            "clusters": [...],       # list of cluster dicts
            "noise_count": int,      # tickets not in any cluster
            "total_tickets": int,
            "df_with_cluster": df,   # original df + 'cluster_id' column
          }
        """
        if df.empty:
            return {"clusters": [], "noise_count": 0, "total_tickets": 0, "df_with_cluster": df}

        texts = df["full_text"].fillna("").tolist()
        cleaned = [_clean(t) for t in texts]

        # Vectorize
        self._vectorizer = TfidfVectorizer(
            max_features=TFIDF_MAX_FEATURES,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
            stop_words=list(STOP_WORDS),
        )
        try:
            X = self._vectorizer.fit_transform(cleaned)
        except ValueError:
            # Not enough data to vectorize
            df_out = df.copy()
            df_out["cluster_id"] = -1
            return {
                "clusters": [],
                "noise_count": len(df),
                "total_tickets": len(df),
                "df_with_cluster": df_out,
            }

        # Compute cosine distance matrix
        # For large datasets, use sparse-friendly approach
        if X.shape[0] <= 5000:
            dist_matrix = 1 - cosine_similarity(X)
            np.clip(dist_matrix, 0, None, out=dist_matrix)  # fix float errors
            db = DBSCAN(
                eps=self.eps,
                min_samples=self.min_samples,
                metric="precomputed",
                n_jobs=-1,
            ).fit(dist_matrix)
        else:
            # For large sets, use approximate with euclidean on dense TF-IDF
            db = DBSCAN(
                eps=self.eps,
                min_samples=self.min_samples,
                metric="cosine",
                n_jobs=-1,
                algorithm="brute",
            ).fit(X)

        labels = db.labels_
        df_out = df.copy()
        df_out["cluster_id"] = labels

        # Build cluster metadata
        clusters = []
        unique_labels = sorted(set(labels))

        for lbl in unique_labels:
            if lbl == -1:
                continue  # noise
            mask = labels == lbl
            cluster_df = df.loc[mask]

            if len(cluster_df) < self.min_cluster_size:
                # Re-label small clusters as noise
                df_out.loc[df_out["cluster_id"] == lbl, "cluster_id"] = -1
                continue

            cluster_texts = cluster_df["full_text"].tolist()
            keywords = _top_keywords(cluster_texts, n=6)

            priority_dist = (
                cluster_df["priority"]
                .value_counts()
                .reindex(["P1", "P2", "P3", "P4", "Unknown"], fill_value=0)
                .to_dict()
            )

            services = [
                s for s in cluster_df["business_service"].dropna().tolist() if s
            ]
            top_services = [s for s, _ in Counter(services).most_common(3)]

            cis = [s for s in cluster_df["cmdb_ci"].dropna().tolist() if s]
            top_cis = [s for s, _ in Counter(cis).most_common(3)]

            groups = [s for s in cluster_df["assignment_group"].dropna().tolist() if s]
            top_groups = [s for s, _ in Counter(groups).most_common(3)]

            states = cluster_df["state"].value_counts().to_dict()

            avg_mttr = (
                cluster_df["mttr_hours"].dropna().mean()
                if "mttr_hours" in cluster_df.columns
                else None
            )

            first_seen = cluster_df["opened_at"].min()
            last_seen = cluster_df["opened_at"].max()

            clusters.append(
                {
                    "id": int(lbl),
                    "label": _label_cluster(keywords),
                    "keywords": keywords,
                    "size": int(len(cluster_df)),
                    "ticket_numbers": cluster_df["number"].tolist(),
                    "priority_dist": priority_dist,
                    "top_services": top_services,
                    "top_cis": top_cis,
                    "top_groups": top_groups,
                    "state_dist": states,
                    "avg_mttr_hours": round(avg_mttr, 1) if avg_mttr else None,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "recurrence": _estimate_recurrence(cluster_df["opened_at"]),
                    "trend": _trend(cluster_df),
                    "category": cluster_df["category"].mode()[0]
                    if not cluster_df["category"].empty
                    else "Unknown",
                }
            )

        # Sort by size descending
        clusters.sort(key=lambda c: c["size"], reverse=True)

        noise_count = int((df_out["cluster_id"] == -1).sum())

        return {
            "clusters": clusters,
            "noise_count": noise_count,
            "total_tickets": len(df),
            "df_with_cluster": df_out,
        }

    # ------------------------------------------------------------------

    def find_similar(self, df: pd.DataFrame, query: str, top_n: int = 10) -> pd.DataFrame:
        """Find tickets most similar to a query string."""
        if self._vectorizer is None:
            raise RuntimeError("Call detect() first to fit the vectorizer.")
        texts = df["full_text"].fillna("").tolist()
        X = self._vectorizer.transform([_clean(t) for t in texts])
        q_vec = self._vectorizer.transform([_clean(query)])
        sims = cosine_similarity(q_vec, X).flatten()
        top_idx = sims.argsort()[-top_n:][::-1]
        result = df.iloc[top_idx].copy()
        result["similarity_score"] = sims[top_idx]
        return result
