#!/usr/bin/env python3
"""
AI Data Quality Checker
========================
Scans a CSV file for data quality issues (missing values, duplicates,
outliers, inconsistencies) and uses the Claude API to produce a
plain-English report of the findings.
"""

import argparse
import json
import sys
import re
from pathlib import Path

import pandas as pd
from scipy import stats
import anthropic


# ─────────────────────────────────────────────
# 1. CSV LOADING
# ─────────────────────────────────────────────

def load_csv(path: str) -> pd.DataFrame:
    """Load a CSV file and return a DataFrame."""
    file_path = Path(path)
    if not file_path.exists():
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        sys.exit(1)
    if file_path.suffix.lower() != ".csv":
        print(f"[WARNING] File does not have a .csv extension: {path}", file=sys.stderr)

    try:
        df = pd.read_csv(path)
        print(f"[✓] Loaded '{file_path.name}'  —  {len(df):,} rows × {len(df.columns)} columns\n")
        return df
    except Exception as exc:
        print(f"[ERROR] Could not read CSV: {exc}", file=sys.stderr)
        sys.exit(1)


# ─────────────────────────────────────────────
# 2. DATA QUALITY SCANNING
# ─────────────────────────────────────────────

def scan_missing_values(df: pd.DataFrame) -> dict:
    """Return per-column and total missing-value counts."""
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    per_column = {
        col: {"count": int(missing[col]), "pct": float(missing_pct[col])}
        for col in df.columns
        if missing[col] > 0
    }
    return {
        "total_missing_cells": int(missing.sum()),
        "total_cells": int(df.size),
        "overall_completeness_pct": round(100 - missing.sum() / df.size * 100, 2),
        "columns_with_missing": per_column,
    }


def scan_duplicates(df: pd.DataFrame) -> dict:
    """Detect exact duplicate rows."""
    dup_mask = df.duplicated(keep="first")
    dup_rows = df[dup_mask].index.tolist()
    return {
        "duplicate_row_count": int(dup_mask.sum()),
        "duplicate_row_indices": dup_rows[:20],  # cap at 20 for brevity
    }


def scan_outliers(df: pd.DataFrame) -> dict:
    """Use IQR and Z-score methods to find numeric outliers."""
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    outlier_summary = {}

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 4:
            continue

        # IQR method
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        iqr_outliers = series[(series < lower) | (series > upper)]

        # Z-score method (|z| > 3)
        z_scores = stats.zscore(series)
        z_outliers = series[abs(z_scores) > 3]

        if len(iqr_outliers) > 0 or len(z_outliers) > 0:
            outlier_summary[col] = {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": round(float(series.mean()), 2),
                "iqr_outlier_count": int(len(iqr_outliers)),
                "iqr_outlier_values": iqr_outliers.tolist()[:10],
                "zscore_outlier_count": int(len(z_outliers)),
                "zscore_outlier_values": z_outliers.tolist()[:10],
            }

    return {"columns_with_outliers": outlier_summary}


def scan_inconsistencies(df: pd.DataFrame) -> dict:
    """
    Detect common inconsistencies:
      - Mixed-case entries in string columns (e.g. 'Engineering' vs 'engineering')
      - Columns that look like emails but contain invalid addresses
      - Date columns where some values can't be parsed
      - Numeric-looking columns stored as strings with negative values where unexpected
    """
    issues = {}

    for col in df.columns:
        col_issues = []
        series = df[col].dropna().astype(str)

        # --- Mixed case categories ---
        unique_vals = series.unique()
        lower_set = set(v.lower() for v in unique_vals)
        if len(lower_set) < len(unique_vals):
            mixed = [v for v in unique_vals if series.str.lower().str.count(re.escape(v.lower())).sum() == 0]
            col_issues.append(
                f"Possible mixed-case inconsistency: "
                f"{len(unique_vals)} unique values but only {len(lower_set)} distinct case-insensitive values."
            )

        # --- Invalid email addresses ---
        email_pattern = re.compile(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$")
        if "email" in col.lower() or "mail" in col.lower():
            invalid_emails = [v for v in unique_vals if not email_pattern.match(v)]
            if invalid_emails:
                col_issues.append(
                    f"Invalid email format detected in {len(invalid_emails)} unique value(s): "
                    f"{invalid_emails[:5]}"
                )

        # --- Unparseable dates ---
        if any(kw in col.lower() for kw in ["date", "time", "dt", "created", "updated", "hire"]):
            parse_failures = 0
            for v in unique_vals:
                try:
                    pd.to_datetime(v)
                except (ValueError, TypeError):
                    parse_failures += 1
            if parse_failures > 0:
                col_issues.append(
                    f"{parse_failures} unique value(s) could not be parsed as dates."
                )

        # --- Negative values in likely non-negative columns ---
        numeric_like_cols = ["age", "salary", "score", "count", "quantity", "price", "amount", "id"]
        if any(kw in col.lower() for kw in numeric_like_cols):
            try:
                numeric_series = pd.to_numeric(df[col], errors="coerce").dropna()
                negatives = numeric_series[numeric_series < 0]
                if not negatives.empty:
                    col_issues.append(
                        f"{len(negatives)} negative value(s) found (e.g. {negatives.tolist()[:5]})."
                    )
            except Exception:
                pass

        if col_issues:
            issues[col] = col_issues

    return {"inconsistency_details": issues}


def build_summary(df: pd.DataFrame, path: str) -> dict:
    """Run all scans and compile a structured summary dict."""
    print("🔍 Scanning for data quality issues...")

    summary = {
        "file": Path(path).name,
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "column_names": df.columns.tolist(),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "missing_values": scan_missing_values(df),
        "duplicates": scan_duplicates(df),
        "outliers": scan_outliers(df),
        "inconsistencies": scan_inconsistencies(df),
    }

    print("  [✓] Missing values scanned")
    print("  [✓] Duplicates scanned")
    print("  [✓] Outliers scanned")
    print("  [✓] Inconsistencies scanned\n")

    return summary


# ─────────────────────────────────────────────
# 3. CLAUDE API CALL
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior data quality analyst. You will receive a JSON summary of \
data quality findings for a CSV file. Your job is to write a clear, \
plain-English report aimed at a business analyst or data engineer who is \
NOT necessarily a statistician.

Format your response as follows:
1. A brief overview (2-3 sentences).
2. A bulleted list of key issues found, grouped by category \
   (Missing Values, Duplicates, Outliers, Inconsistencies).
3. A short "Recommendations" section with actionable next steps.

Be concise but thorough. Use plain language — avoid jargon. \
If an issue is minor, say so. If it's critical, flag it clearly.\
"""

def call_claude(summary: dict) -> str:
    """Send the quality summary to Claude and return the plain-English report."""
    client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY from env

    user_message = (
        "Here is the data quality summary JSON. Please write the report:\n\n"
        + json.dumps(summary, indent=2)
    )

    print("🤖 Sending findings to Claude (claude-sonnet-4-6)...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text


# ─────────────────────────────────────────────
# 4. MAIN / CLI
# ─────────────────────────────────────────────

def print_report(report: str) -> None:
    """Pretty-print the Claude report to the terminal."""
    border = "━" * 60
    print(f"\n{border}")
    print("  📊  DATA QUALITY REPORT")
    print(f"{border}\n")
    print(report)
    print(f"\n{border}\n")


def main():
    parser = argparse.ArgumentParser(
        prog="ai-data-quality-checker",
        description=(
            "Load a CSV file, scan it for data quality issues, "
            "and get a plain-English AI report powered by Claude."
        ),
    )
    parser.add_argument(
        "csv_file",
        help="Path to the CSV file you want to check.",
    )
    parser.add_argument(
        "--dump-summary",
        action="store_true",
        help="Also print the raw JSON summary before the AI report.",
    )
    args = parser.parse_args()

    # Step 1 – Load
    df = load_csv(args.csv_file)

    # Step 2 – Scan
    summary = build_summary(df, args.csv_file)

    if args.dump_summary:
        print("─── Raw JSON Summary ───")
        print(json.dumps(summary, indent=2))
        print("────────────────────────\n")

    # Step 3 – Claude report
    report = call_claude(summary)

    # Step 4 – Print
    print_report(report)


if __name__ == "__main__":
    main()
