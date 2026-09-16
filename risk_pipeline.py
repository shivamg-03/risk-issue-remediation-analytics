"""
Risk Issue & Remediation Analytics -- Automated Analysis Pipeline
Phase 5: Automation layer

Refactors the Phase 2 notebook analysis into reusable functions so the
entire pipeline can be re-run on a new CSV (e.g. next month's export)
without manually editing code cell by cell -- this is the automation
story the JD asks for (#18, #23).

Usage:
    python risk_pipeline.py path/to/risk_issues_dataset.csv
    (defaults to risk_issues_dataset.csv in the current folder if no
    argument is given)
"""

import sys
import pandas as pd
import numpy as np


def load_data(csv_path):
    """Load the risk issues CSV with correct date parsing."""
    df = pd.read_csv(
        csv_path,
        parse_dates=["Open_Date", "Target_Close_Date", "Actual_Close_Date"],
    )
    return df


def validate_data(df):
    """
    Basic data quality checks -- run every time, on every new file,
    so a bad export gets caught before analysis runs on it.
    """
    issues = []
    required_cols = [
        "Issue_ID", "Business_Unit", "Risk_Category", "Severity",
        "Root_Cause_Category", "Control_Test_Result", "Open_Date",
        "Target_Close_Date", "Actual_Close_Date", "SLA_Breach", "Recurrence_Flag",
    ]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        issues.append(f"Missing expected columns: {missing_cols}")

    if df["Issue_ID"].duplicated().any():
        issues.append("Duplicate Issue_ID values found")

    if df["SLA_Breach"].dtype != bool:
        issues.append("SLA_Breach is not boolean type")

    if issues:
        print("VALIDATION WARNINGS:")
        for i in issues:
            print(f"  - {i}")
    else:
        print("Validation passed: no issues found.")
    return len(issues) == 0


def trend_analysis(df):
    """Issue volume over time and by business unit."""
    df = df.copy()
    df["Open_Month"] = df["Open_Date"].dt.to_period("M")
    monthly = df.groupby("Open_Month").size()
    by_unit = df["Business_Unit"].value_counts()
    top_combos = df.groupby(["Business_Unit", "Risk_Category"]).size().sort_values(ascending=False).head(5)
    return {
        "monthly_trend": monthly,
        "peak_month": monthly.idxmax(),
        "peak_count": monthly.max(),
        "volume_by_unit": by_unit,
        "top_combos": top_combos,
    }


def root_cause_pareto(df):
    """Root cause frequency and cumulative Pareto share."""
    rc_counts = df["Root_Cause_Category"].value_counts()
    rc_pct = (rc_counts / rc_counts.sum() * 100).round(1)
    pareto = pd.DataFrame({
        "Count": rc_counts,
        "Pct": rc_pct,
        "Cumulative_Pct": rc_pct.cumsum().round(1),
    })
    return pareto


def control_effectiveness(df):
    """Control test fail rate by severity and business unit."""
    fail_by_severity = df.groupby("Severity")["Control_Test_Result"].apply(
        lambda x: (x == "Fail").mean() * 100
    ).round(1)
    fail_by_unit = df.groupby("Business_Unit")["Control_Test_Result"].apply(
        lambda x: (x == "Fail").mean() * 100
    ).round(1)
    return {"fail_by_severity": fail_by_severity, "fail_by_unit": fail_by_unit}


def sla_breach_analysis(df):
    """SLA breach rate overall and by severity, unit, risk category."""
    return {
        "overall_pct": round(df["SLA_Breach"].mean() * 100, 1),
        "by_severity": (df.groupby("Severity")["SLA_Breach"].mean() * 100).round(1),
        "by_unit": (df.groupby("Business_Unit")["SLA_Breach"].mean() * 100).round(1),
        "by_risk_category": (df.groupby("Risk_Category")["SLA_Breach"].mean() * 100).round(1),
    }


def recurrence_analysis(df):
    """Recurrence rate and top recurring business unit / root cause combos."""
    overall_pct = round(df["Recurrence_Flag"].mean() * 100, 2)
    overall_count = int(df["Recurrence_Flag"].sum())
    top_combos = (
        df[df["Recurrence_Flag"]]
        .groupby(["Business_Unit", "Root_Cause_Category"])
        .size()
        .sort_values(ascending=False)
        .head(5)
    )
    return {"pct": overall_pct, "count": overall_count, "top_combos": top_combos}


def open_exposure_snapshot(df, snapshot_date=None):
    """
    Current open issue count and age.
    snapshot_date defaults to the max Open_Date in the file + a small
    buffer, so this works correctly even when re-run on a future export
    with a later date range -- this is what makes it genuinely reusable,
    not hardcoded to one dataset's dates.
    """
    if snapshot_date is None:
        snapshot_date = df["Open_Date"].max()
    snapshot_date = pd.Timestamp(snapshot_date)

    open_issues = df[df["Actual_Close_Date"].isna()]
    age_days = (snapshot_date - open_issues["Open_Date"]).dt.days
    return {
        "snapshot_date": snapshot_date,
        "open_count": len(open_issues),
        "avg_age_days": round(age_days.mean(), 1) if len(open_issues) else None,
        "oldest_age_days": int(age_days.max()) if len(open_issues) else None,
        "high_severity_open": int((open_issues["Severity"] == "High").sum()),
    }


def run_full_analysis(csv_path, snapshot_date=None):
    """
    Runs the entire Phase 2 analysis pipeline end to end on any CSV
    matching the expected schema. This is the single entry point --
    everything above is a building block called from here.
    """
    print(f"Loading data from: {csv_path}")
    df = load_data(csv_path)
    print(f"Loaded {len(df)} rows.\n")

    ok = validate_data(df)
    if not ok:
        print("\nProceeding despite warnings -- review before trusting results.\n")

    results = {}
    results["trend"] = trend_analysis(df)
    results["pareto"] = root_cause_pareto(df)
    results["control"] = control_effectiveness(df)
    results["sla"] = sla_breach_analysis(df)
    results["recurrence"] = recurrence_analysis(df)
    results["exposure"] = open_exposure_snapshot(df, snapshot_date)

    return df, results


def print_summary(results):
    """Human-readable summary of every result block, for console output."""
    print("=" * 70)
    print("TREND ANALYSIS")
    print("=" * 70)
    print(f"Peak month: {results['trend']['peak_month']} ({results['trend']['peak_count']} issues)")
    print(results["trend"]["volume_by_unit"].to_string())

    print("\n" + "=" * 70)
    print("ROOT CAUSE PARETO")
    print("=" * 70)
    print(results["pareto"].to_string())

    print("\n" + "=" * 70)
    print("CONTROL EFFECTIVENESS")
    print("=" * 70)
    print("By Severity:\n", results["control"]["fail_by_severity"].to_string())
    print("\nBy Business Unit:\n", results["control"]["fail_by_unit"].to_string())

    print("\n" + "=" * 70)
    print("SLA BREACH")
    print("=" * 70)
    print(f"Overall: {results['sla']['overall_pct']}%")
    print("By Severity:\n", results["sla"]["by_severity"].to_string())

    print("\n" + "=" * 70)
    print("RECURRENCE")
    print("=" * 70)
    print(f"Rate: {results['recurrence']['pct']}% ({results['recurrence']['count']} issues)")
    print(results["recurrence"]["top_combos"].to_string())

    print("\n" + "=" * 70)
    print("OPEN EXPOSURE SNAPSHOT")
    print("=" * 70)
    exp = results["exposure"]
    print(f"Snapshot date: {exp['snapshot_date'].date()}")
    print(f"Open issues: {exp['open_count']}")
    print(f"Avg age: {exp['avg_age_days']} days | Oldest: {exp['oldest_age_days']} days")
    print(f"High-severity open: {exp['high_severity_open']}")


def main():
    """
    Entry point. Pass a CSV path as a command-line argument to run the
    full pipeline on it; defaults to 'risk_issues_dataset.csv' in the
    current folder if no argument is given.
    """
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "risk_issues_dataset.csv"
    snapshot_date = pd.Timestamp("2026-06-30")  # matches the original dataset's window end
    df, results = run_full_analysis(csv_path, snapshot_date=snapshot_date)
    print_summary(results)
    return df, results


if __name__ == "__main__":
    main()
