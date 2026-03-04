"""
Data ingestion: CSV files and ServiceNow REST API.

Both paths produce the same normalized pandas DataFrame so the rest of the
pipeline doesn't need to care about the source.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from config import COLUMN_ALIASES, PRIORITY_MAP, STATE_MAP, SNOW_API_PAGE_SIZE, SNOW_API_TIMEOUT


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class DataLoader:
    """Load and normalize ServiceNow ticket data from CSV or REST API."""

    # Required normalized columns and their default fill values
    REQUIRED_COLUMNS: dict[str, object] = {
        "number": "",
        "short_description": "",
        "description": "",
        "category": "",
        "subcategory": "",
        "priority": "Unknown",
        "impact": "Unknown",
        "urgency": "Unknown",
        "state": "Unknown",
        "assigned_to": "Unassigned",
        "assignment_group": "Unassigned",
        "opened_at": pd.NaT,
        "resolved_at": pd.NaT,
        "closed_at": pd.NaT,
        "cmdb_ci": "",
        "business_service": "",
        "close_notes": "",
        "root_cause": "",
        "record_type": "Incident",
        "type": "",
        "caller": "",
    }

    # ------------------------------------------------------------------ CSV

    def load_csv(self, path: str | Path, encoding: str = "utf-8") -> pd.DataFrame:
        """Load one or more CSV files (glob supported) and return normalized df."""
        path = Path(path)
        if path.is_dir():
            files = list(path.glob("*.csv"))
        elif "*" in str(path) or "?" in str(path):
            import glob as _glob
            files = [Path(p) for p in _glob.glob(str(path))]
        else:
            files = [path]

        if not files:
            raise FileNotFoundError(f"No CSV files found at: {path}")

        frames = []
        for f in files:
            try:
                df = pd.read_csv(f, encoding=encoding, low_memory=False)
                frames.append(df)
            except UnicodeDecodeError:
                df = pd.read_csv(f, encoding="latin-1", low_memory=False)
                frames.append(df)

        raw = pd.concat(frames, ignore_index=True)
        return self._normalize(raw)

    # ------------------------------------------------------------------ API

    def load_api(
        self,
        instance_url: str,
        table: str = "incident",
        days: int = 30,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        extra_filters: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch tickets from ServiceNow Table API.

        Authentication priority: bearer token > basic auth > env vars.
        """
        base = instance_url.rstrip("/")
        endpoint = f"{base}/api/now/table/{table}"

        # Build auth
        auth = None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            auth = HTTPBasicAuth(username, password)
        else:
            env_user = os.getenv("SNOW_USERNAME")
            env_pass = os.getenv("SNOW_PASSWORD")
            env_token = os.getenv("SNOW_TOKEN")
            if env_token:
                headers["Authorization"] = f"Bearer {env_token}"
            elif env_user and env_pass:
                auth = HTTPBasicAuth(env_user, env_pass)

        # Date filter
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        sysparm_query = f"opened_at>={since}"
        if extra_filters:
            sysparm_query += f"^{extra_filters}"

        records: list[dict] = []
        offset = 0

        while True:
            params = {
                "sysparm_query": sysparm_query,
                "sysparm_limit": SNOW_API_PAGE_SIZE,
                "sysparm_offset": offset,
                "sysparm_display_value": "true",
                "sysparm_exclude_reference_link": "true",
            }
            resp = requests.get(
                endpoint,
                params=params,
                headers=headers,
                auth=auth,
                timeout=SNOW_API_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("result", [])
            if not data:
                break
            records.extend(data)
            if len(data) < SNOW_API_PAGE_SIZE:
                break
            offset += SNOW_API_PAGE_SIZE

        if not records:
            return self._normalize(pd.DataFrame())

        raw = pd.json_normalize(records)
        return self._normalize(raw)

    # ------------------------------------------------------------------ JSON

    def load_json(self, path: str | Path) -> pd.DataFrame:
        """Load a JSON export (list of records or ServiceNow API response)."""
        path = Path(path)
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        raw = pd.json_normalize(data)
        return self._normalize(raw)

    # -------------------------------------------------------------- normalize

    def _normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw.empty:
            return pd.DataFrame(columns=list(self.REQUIRED_COLUMNS.keys()))

        df = raw.copy()

        # 1. Rename columns using alias table (case-insensitive)
        col_map = {
            c: COLUMN_ALIASES[c.lower().strip()]
            for c in df.columns
            if c.lower().strip() in COLUMN_ALIASES
        }
        df = df.rename(columns=col_map)

        # 2. Deduplicate columns (keep first occurrence)
        df = df.loc[:, ~df.columns.duplicated()]

        # 3. Ensure all required columns exist
        for col, default in self.REQUIRED_COLUMNS.items():
            if col not in df.columns:
                df[col] = default

        # Keep only normalized columns + any extras the caller might want
        df = df[list(self.REQUIRED_COLUMNS.keys()) + [
            c for c in df.columns if c not in self.REQUIRED_COLUMNS
        ]]

        # 4. Clean string columns
        for col in ["short_description", "description", "close_notes", "root_cause"]:
            df[col] = df[col].fillna("").astype(str).str.strip()

        # 5. Combine short + long description into a single analysis text
        df["full_text"] = (df["short_description"] + " " + df["description"]).str.strip()

        # 6. Normalize priority
        df["priority"] = (
            df["priority"].fillna("").astype(str).str.strip().str.lower()
            .map(lambda v: PRIORITY_MAP.get(v, "Unknown"))
        )

        # 7. Normalize state
        df["state"] = (
            df["state"].fillna("").astype(str).str.strip().str.lower()
            .map(lambda v: STATE_MAP.get(v, v.title() if v else "Unknown"))
        )

        # 8. Parse datetime columns
        for dt_col in ["opened_at", "resolved_at", "closed_at"]:
            df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce", utc=True)

        # 9. Derive MTTR (hours) where possible
        resolution_time = df["resolved_at"].fillna(df["closed_at"])
        df["mttr_hours"] = (
            (resolution_time - df["opened_at"]).dt.total_seconds() / 3600
        ).where(df["opened_at"].notna())
        df["mttr_hours"] = df["mttr_hours"].where(df["mttr_hours"] > 0)

        # 10. Derive age (hours since opened, for still-open tickets)
        now = pd.Timestamp.now(tz="UTC")
        df["age_hours"] = (
            (now - df["opened_at"]).dt.total_seconds() / 3600
        ).where(df["opened_at"].notna())

        # 11. Infer record_type if blank
        df["record_type"] = df["record_type"].fillna("").astype(str).str.strip()
        mask_empty = df["record_type"] == ""
        df.loc[mask_empty & df["number"].str.startswith("INC", na=False), "record_type"] = "Incident"
        df.loc[mask_empty & df["number"].str.startswith("CHG", na=False), "record_type"] = "Change"
        df.loc[mask_empty & df["number"].str.startswith("PRB", na=False), "record_type"] = "Problem"
        df.loc[mask_empty & (df["record_type"] == ""), "record_type"] = "Incident"

        # 12. Remove duplicate ticket numbers
        df = df.drop_duplicates(subset=["number"], keep="last").reset_index(drop=True)

        return df
