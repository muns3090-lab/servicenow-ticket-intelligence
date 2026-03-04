"""
Auto-classification of tickets.

Strategy (layered, fastest-first):
  1. Ticket already has a valid category → keep it.
  2. Rule-based keyword scan of full_text → fast and interpretable.
  3. TF-IDF + cosine similarity to labeled seed vectors → ML fallback
     (only activated when ≥20 labeled tickets exist).
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import CATEGORY_KEYWORDS, TFIDF_MAX_FEATURES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


KNOWN_CATEGORIES = set(CATEGORY_KEYWORDS.keys())

# Pre-compile keyword patterns for speed
_KW_PATTERNS: dict[str, re.Pattern] = {
    cat: re.compile(
        r"\b(" + "|".join(re.escape(kw) for kw in kws) + r")\b",
        re.IGNORECASE,
    )
    for cat, kws in CATEGORY_KEYWORDS.items()
}


def _rule_classify(text: str) -> str | None:
    """Return best rule-based category or None if no match."""
    cleaned = _clean(text)
    best_cat = None
    best_count = 0
    for cat, pattern in _KW_PATTERNS.items():
        matches = len(pattern.findall(cleaned))
        if matches > best_count:
            best_count = matches
            best_cat = cat
    return best_cat  # None if best_count == 0


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class TicketClassifier:
    """
    Classify / fill-in missing ticket categories.

    Usage:
        clf = TicketClassifier()
        df = clf.fit_classify(df)
    """

    def __init__(self, min_labeled: int = 20):
        self.min_labeled = min_labeled
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._label_vectors: Optional[np.ndarray] = None
        self._label_names: Optional[list[str]] = None
        self._ml_ready = False

    # ------------------------------------------------------------------

    def fit_classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Classify all tickets. Modifies 'category' in-place where missing/unknown.
        Adds 'category_source' column: 'original' | 'rule' | 'ml' | 'uncategorized'.
        """
        df = df.copy()
        df["category_source"] = "original"

        # Normalize category column
        df["category"] = df["category"].fillna("").astype(str).str.strip()

        # Identify tickets that need classification
        needs_class = (
            df["category"].isin(["", "Unknown", "Other", "N/A"])
            | ~df["category"].isin(KNOWN_CATEGORIES)
        )

        # Fit ML model on the labeled portion if enough data
        labeled_mask = ~needs_class
        if labeled_mask.sum() >= self.min_labeled:
            self._fit_ml(df[labeled_mask])

        # Classify unlabeled tickets
        for idx in df[needs_class].index:
            text = df.at[idx, "full_text"]
            cat = _rule_classify(text)
            if cat:
                df.at[idx, "category"] = cat
                df.at[idx, "category_source"] = "rule"
            elif self._ml_ready:
                cat = self._ml_predict_one(text)
                df.at[idx, "category"] = cat
                df.at[idx, "category_source"] = "ml"
            else:
                df.at[idx, "category"] = "Other"
                df.at[idx, "category_source"] = "uncategorized"

        # Also classify tickets with known categories using our taxonomy
        # (to handle ServiceNow's own category names that differ from ours)
        for idx in df[~needs_class].index:
            cat = df.at[idx, "category"]
            if cat not in KNOWN_CATEGORIES:
                # Try to map via rule-based on the category string itself
                mapped = _rule_classify(cat)
                if mapped:
                    df.at[idx, "category"] = mapped
                    df.at[idx, "category_source"] = "rule"

        return df

    # ------------------------------------------------------------------

    def _fit_ml(self, labeled_df: pd.DataFrame) -> None:
        """Fit TF-IDF on labeled data; build per-class centroid vectors."""
        texts = labeled_df["full_text"].fillna("").tolist()
        labels = labeled_df["category"].tolist()

        self._vectorizer = TfidfVectorizer(
            max_features=TFIDF_MAX_FEATURES,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
        )
        X = self._vectorizer.fit_transform(texts)

        # Build per-class centroid
        unique_labels = list(dict.fromkeys(labels))  # preserve order, unique
        centroids = []
        for lbl in unique_labels:
            mask = [l == lbl for l in labels]
            centroid = X[mask].mean(axis=0)
            centroids.append(np.asarray(centroid).flatten())

        self._label_vectors = np.vstack(centroids)
        self._label_names = unique_labels
        self._ml_ready = True

    def _ml_predict_one(self, text: str) -> str:
        vec = self._vectorizer.transform([text])
        sims = cosine_similarity(vec, self._label_vectors).flatten()
        best = int(np.argmax(sims))
        if sims[best] < 0.05:
            return "Other"
        return self._label_names[best]

    # ------------------------------------------------------------------

    @staticmethod
    def classification_summary(df: pd.DataFrame) -> pd.DataFrame:
        """Return a summary table of category distribution and source."""
        return (
            df.groupby(["category", "category_source"])
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
