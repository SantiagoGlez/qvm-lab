#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from datetime import datetime

import pandas as pd


REQUIRED_COLUMNS = {
    "year",
    "revenue",
    "eps",
    "net_income",
    "operating_margin",
    "cash",
    "total_debt",
    "total_assets",
    "net_assets",
    "pe_ratio",
}

OPTIONAL_COLUMNS = {
    "total_liabilities",
    "shares_outstanding",
    "dividend_yield",
    "price_to_sales",
    "price_to_book",
}

EXPECTED_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS
OLDEST_WINDOW_YEARS = 5
NON_NEGATIVE_COLUMNS = {
    "revenue",
    "cash",
    "total_debt",
    "total_assets",
    "total_liabilities",
    "shares_outstanding",
    "dividend_yield",
    "price_to_sales",
}


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def read_financials_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    normalized = {column: column.strip().lower() for column in df.columns}
    df = df.rename(columns=normalized)
    return df


def _extract_ticker(path: Path) -> str:
    stem = path.stem
    if stem.endswith("_financials"):
        stem = stem[: -len("_financials")]
    return stem.split("_")[0].upper()


def _year_profile(df: pd.DataFrame) -> dict[str, Any]:
    if "year" not in df.columns:
        return {
            "historical_years": 0,
            "first_year": None,
            "last_year": None,
        }

    years = _to_numeric(df["year"]).dropna().astype(int)
    if years.empty:
        return {
            "historical_years": 0,
            "first_year": None,
            "last_year": None,
        }

    unique_years = sorted(set(years.tolist()))
    return {
        "historical_years": len(unique_years),
        "first_year": min(unique_years),
        "last_year": max(unique_years),
    }


def _column_presence(df: pd.DataFrame) -> dict[str, list[str]]:
    available = sorted(set(df.columns) & EXPECTED_COLUMNS)
    missing = sorted(EXPECTED_COLUMNS - set(df.columns))
    extras = sorted(set(df.columns) - EXPECTED_COLUMNS)
    return {
        "available": available,
        "missing": missing,
        "extras": extras,
    }


def _missing_value_counts(df: pd.DataFrame, columns: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column in columns:
        if column not in df.columns:
            continue
        if column == "year":
            series = _to_numeric(df[column])
        else:
            series = _to_numeric(df[column])
        counts[column] = int(series.isna().sum())
    return counts


def _series_if_present(df: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in df.columns:
        return None
    return _to_numeric(df[column])


def _build_sanity_checks(df: pd.DataFrame, year_profile: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "issues": [],
        "counts": {},
    }

    # Duplicate years reduce confidence in historical interpretation.
    if "year" in df.columns:
        year_values = _to_numeric(df["year"]).dropna().astype(int).tolist()
        unique_years = set(year_values)
        duplicate_years = len(year_values) - len(unique_years)
        checks["counts"]["duplicate_year_rows"] = duplicate_years
        if duplicate_years > 0:
            checks["issues"].append(f"duplicate_year_rows={duplicate_years}")

    # Year bounds should be plausible for modern public-company data.
    if year_profile["first_year"] is not None and year_profile["first_year"] < 1900:
        checks["issues"].append(f"first_year_too_old={year_profile['first_year']}")
    if year_profile["last_year"] is not None:
        current_year = datetime.now().year
        if year_profile["last_year"] > current_year + 1:
            checks["issues"].append(f"last_year_future={year_profile['last_year']}")

    for column in sorted(NON_NEGATIVE_COLUMNS):
        series = _series_if_present(df, column)
        if series is None:
            continue
        negative_count = int((series < 0).fillna(False).sum())
        checks["counts"][f"negative_{column}"] = negative_count
        if negative_count > 0:
            checks["issues"].append(f"negative_{column}={negative_count}")

    # Operating margin is expressed as percentage points in source pages.
    operating_margin = _series_if_present(df, "operating_margin")
    if operating_margin is not None:
        out_of_range = int(((operating_margin < -100) | (operating_margin > 100)).fillna(False).sum())
        checks["counts"]["operating_margin_out_of_range"] = out_of_range
        if out_of_range > 0:
            checks["issues"].append(f"operating_margin_out_of_range={out_of_range}")

    # Dividend yield should generally be a reasonable percentage.
    dividend_yield = _series_if_present(df, "dividend_yield")
    if dividend_yield is not None:
        out_of_range = int((dividend_yield > 100).fillna(False).sum())
        checks["counts"]["dividend_yield_gt_100"] = out_of_range
        if out_of_range > 0:
            checks["issues"].append(f"dividend_yield_gt_100={out_of_range}")

    # Balance sheet identity consistency when all three fields exist in a row.
    assets = _series_if_present(df, "total_assets")
    liabilities = _series_if_present(df, "total_liabilities")
    net_assets = _series_if_present(df, "net_assets")
    if assets is not None and liabilities is not None and net_assets is not None:
        mask = assets.notna() & liabilities.notna() & net_assets.notna()
        comparable_rows = int(mask.sum())
        mismatch_rows = 0
        if comparable_rows > 0:
            expected_net_assets = assets[mask] - liabilities[mask]
            tolerance = assets[mask].abs() * 0.01
            diff = (expected_net_assets - net_assets[mask]).abs()
            mismatch_rows = int((diff > tolerance).sum())
        checks["counts"]["balance_identity_rows"] = comparable_rows
        checks["counts"]["balance_identity_mismatch_rows"] = mismatch_rows
        if comparable_rows > 0 and mismatch_rows > 0:
            checks["issues"].append(
                f"balance_identity_mismatch_rows={mismatch_rows}/{comparable_rows}"
            )

    checks["issue_count"] = len(checks["issues"])
    return checks


def _oldest_window_profile(
    df: pd.DataFrame,
    available_columns: list[str],
    oldest_years: int = OLDEST_WINDOW_YEARS,
) -> dict[str, Any]:
    if "year" not in df.columns:
        return {
            "years": [],
            "row_count": 0,
            "missing_values": {},
            "sanity_checks": {"issues": [], "counts": {}, "issue_count": 0},
        }

    year_series = _to_numeric(df["year"])
    valid_years = sorted({int(y) for y in year_series.dropna().tolist()})
    selected_years = valid_years[:oldest_years]
    if not selected_years:
        return {
            "years": [],
            "row_count": 0,
            "missing_values": {},
            "sanity_checks": {"issues": [], "counts": {}, "issue_count": 0},
        }

    subset = df.loc[year_series.isin(selected_years)].copy()
    missing_values = _missing_value_counts(subset, ["year"] + available_columns)
    sanity_checks = _build_sanity_checks(subset, _year_profile(subset))

    return {
        "years": selected_years,
        "row_count": int(len(subset)),
        "missing_values": missing_values,
        "sanity_checks": sanity_checks,
    }


def _yearly_problem_map(df: pd.DataFrame, available_columns: list[str]) -> dict[str, Any]:
    if "year" not in df.columns:
        return {
            "problem_years": [],
            "by_year": {},
            "oldest_problem_year": None,
            "newest_problem_year": None,
        }

    year_series = _to_numeric(df["year"])
    working = df.copy()
    working["_audit_year"] = year_series
    working = working[working["_audit_year"].notna()].copy()
    if working.empty:
        return {
            "problem_years": [],
            "by_year": {},
            "oldest_problem_year": None,
            "newest_problem_year": None,
        }

    working["_audit_year"] = working["_audit_year"].astype(int)
    expected_present_columns = sorted(c for c in available_columns if c != "year")
    expected_present_set = set(expected_present_columns)
    required_present_set = REQUIRED_COLUMNS & expected_present_set

    by_year: dict[int, dict[str, Any]] = {}
    for year in sorted(working["_audit_year"].unique().tolist()):
        year_frame = working[working["_audit_year"] == year]
        row_count = int(len(year_frame))
        missing_columns: list[str] = []
        missing_required_columns: list[str] = []

        for column in expected_present_columns:
            numeric = _to_numeric(year_frame[column])
            if not numeric.notna().any():
                missing_columns.append(column)
                if column in required_present_set:
                    missing_required_columns.append(column)

        sanity_flags: list[str] = []
        duplicate_count = row_count - 1
        if duplicate_count > 0:
            sanity_flags.append(f"duplicate_year_rows={duplicate_count}")

        for column in sorted(NON_NEGATIVE_COLUMNS & expected_present_set):
            numeric = _to_numeric(year_frame[column])
            negative_count = int((numeric < 0).fillna(False).sum())
            if negative_count > 0:
                sanity_flags.append(f"negative_{column}={negative_count}")

        if "operating_margin" in expected_present_set:
            operating_margin = _to_numeric(year_frame["operating_margin"])
            out_of_range = int(((operating_margin < -100) | (operating_margin > 100)).fillna(False).sum())
            if out_of_range > 0:
                sanity_flags.append(f"operating_margin_out_of_range={out_of_range}")

        if "dividend_yield" in expected_present_set:
            dividend_yield = _to_numeric(year_frame["dividend_yield"])
            out_of_range = int((dividend_yield > 100).fillna(False).sum())
            if out_of_range > 0:
                sanity_flags.append(f"dividend_yield_gt_100={out_of_range}")

        if {
            "total_assets",
            "total_liabilities",
            "net_assets",
        }.issubset(expected_present_set):
            assets = _to_numeric(year_frame["total_assets"])
            liabilities = _to_numeric(year_frame["total_liabilities"])
            net_assets = _to_numeric(year_frame["net_assets"])
            mask = assets.notna() & liabilities.notna() & net_assets.notna()
            comparable_rows = int(mask.sum())
            if comparable_rows > 0:
                expected_net_assets = assets[mask] - liabilities[mask]
                tolerance = assets[mask].abs() * 0.01
                diff = (expected_net_assets - net_assets[mask]).abs()
                mismatch_rows = int((diff > tolerance).sum())
                if mismatch_rows > 0:
                    sanity_flags.append(
                        f"balance_identity_mismatch_rows={mismatch_rows}/{comparable_rows}"
                    )

        if missing_columns or sanity_flags:
            by_year[int(year)] = {
                "row_count": row_count,
                "missing_columns": sorted(missing_columns),
                "missing_required_columns": sorted(missing_required_columns),
                "sanity_flags": sorted(sanity_flags),
            }

    problem_years = sorted(by_year)
    return {
        "problem_years": problem_years,
        "by_year": by_year,
        "oldest_problem_year": min(problem_years) if problem_years else None,
        "newest_problem_year": max(problem_years) if problem_years else None,
    }


def audit_file(path: Path | str, ticker: str | None = None) -> dict[str, Any]:
    csv_path = Path(path)
    df = read_financials_csv(csv_path)

    presence = _column_presence(df)
    year_profile = _year_profile(df)
    missing_counts = _missing_value_counts(df, ["year"] + presence["available"])
    sanity_checks = _build_sanity_checks(df, year_profile)
    oldest_window = _oldest_window_profile(df, presence["available"])
    yearly_problems = _yearly_problem_map(df, presence["available"])

    return {
        "ticker": ticker or _extract_ticker(csv_path),
        "file": csv_path.name,
        "rows": int(len(df)),
        "historical_years": year_profile["historical_years"],
        "first_year": year_profile["first_year"],
        "last_year": year_profile["last_year"],
        "available_columns": presence["available"],
        "missing_columns": presence["missing"],
        "extra_columns": presence["extras"],
        "missing_values": missing_counts,
        "sanity_checks": sanity_checks,
        "oldest_window": oldest_window,
        "yearly_problems": yearly_problems,
    }


def format_company_report(report: dict[str, Any]) -> str:
    lines = [
        "==========================================",
        "CompaniesMarketCap Historical Financials Audit",
        "==========================================",
        "",
        f"Ticker                    {report['ticker']}",
        f"File                      {report['file']}",
        "",
        "Coverage",
        "--------",
        f"Rows                      {report['rows']}",
        f"Historical years          {report['historical_years']}",
        f"First year                {report['first_year'] if report['first_year'] is not None else '-'}",
        f"Last year                 {report['last_year'] if report['last_year'] is not None else '-'}",
        "",
        "Columns",
        "-------",
        f"Available ({len(report['available_columns'])})     {', '.join(report['available_columns']) if report['available_columns'] else '-'}",
        f"Missing ({len(report['missing_columns'])})       {', '.join(report['missing_columns']) if report['missing_columns'] else '-'}",
        f"Extra ({len(report['extra_columns'])})         {', '.join(report['extra_columns']) if report['extra_columns'] else '-'}",
        "",
        "Missing values per column",
        "-------------------------",
    ]

    if not report["missing_values"]:
        lines.append("None")
    else:
        for column in sorted(report["missing_values"]):
            lines.append(f"{column:<25} {report['missing_values'][column]}")

    lines.extend(["", "Sanity checks", "-------------"])
    if report["sanity_checks"]["issues"]:
        for issue in report["sanity_checks"]["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("No sanity issues detected")

    oldest = report["oldest_window"]
    oldest_label = "-"
    if oldest["years"]:
        oldest_label = f"{oldest['years'][0]}-{oldest['years'][-1]}"

    lines.extend(["", f"Oldest years focus (first up to {OLDEST_WINDOW_YEARS})", "-----------------------------------"])
    lines.append(f"Years                     {oldest_label}")
    lines.append(f"Rows                      {oldest['row_count']}")
    lines.append("Missing values in oldest window")
    if oldest["missing_values"]:
        for column in sorted(oldest["missing_values"]):
            lines.append(f"{column:<25} {oldest['missing_values'][column]}")
    else:
        lines.append("None")

    lines.append("Oldest-window sanity issues")
    if oldest["sanity_checks"]["issues"]:
        for issue in oldest["sanity_checks"]["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("None")

    yearly = report["yearly_problems"]
    lines.extend(["", "Problem years map (exact years to inspect)", "------------------------------------"])
    if yearly["problem_years"]:
        lines.append(
            f"Problem year count        {len(yearly['problem_years'])} "
            f"({yearly['oldest_problem_year']}..{yearly['newest_problem_year']})"
        )
        for year in yearly["problem_years"]:
            details = yearly["by_year"][year]
            lines.append(f"{year}: rows={details['row_count']}")
            lines.append(
                "  missing_columns: "
                + (", ".join(details["missing_columns"]) if details["missing_columns"] else "-")
            )
            lines.append(
                "  missing_required_columns: "
                + (
                    ", ".join(details["missing_required_columns"])
                    if details["missing_required_columns"]
                    else "-"
                )
            )
            lines.append(
                "  sanity_flags: "
                + (", ".join(details["sanity_flags"]) if details["sanity_flags"] else "-")
            )
    else:
        lines.append("No problem years detected")

    return "\n".join(lines)


def _aggregate_universe_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    files_audited = len(reports)
    rows_total = sum(int(report["rows"]) for report in reports)
    years = [int(report["historical_years"]) for report in reports]

    full_required = 0
    missing_required_counts = {column: 0 for column in sorted(REQUIRED_COLUMNS)}
    missing_optional_counts = {column: 0 for column in sorted(OPTIONAL_COLUMNS)}

    missing_value_totals: dict[str, int] = {}
    observed_value_totals: dict[str, int] = {}

    sanity_companies_with_issues = 0
    sanity_total_issues = 0
    sanity_issue_histogram: dict[str, int] = {}

    oldest_rows_total = 0
    oldest_missing_value_totals: dict[str, int] = {}
    oldest_observed_value_totals: dict[str, int] = {}
    oldest_sanity_companies_with_issues = 0
    oldest_sanity_total_issues = 0
    oldest_sanity_issue_histogram: dict[str, int] = {}

    problem_year_company_counts: dict[int, int] = {}
    problem_year_flag_counts: dict[int, int] = {}

    for report in reports:
        available = set(report["available_columns"])
        missing = set(report["missing_columns"])

        if REQUIRED_COLUMNS.issubset(available):
            full_required += 1

        for column in REQUIRED_COLUMNS:
            if column in missing:
                missing_required_counts[column] += 1

        for column in OPTIONAL_COLUMNS:
            if column in missing:
                missing_optional_counts[column] += 1

        for column in EXPECTED_COLUMNS | {"year"}:
            if column in available or column == "year":
                observed_value_totals[column] = observed_value_totals.get(column, 0) + int(report["rows"])

        for column, count in report["missing_values"].items():
            missing_value_totals[column] = missing_value_totals.get(column, 0) + int(count)

        issues = report["sanity_checks"]["issues"]
        if issues:
            sanity_companies_with_issues += 1
        sanity_total_issues += int(report["sanity_checks"]["issue_count"])
        for issue in issues:
            key = issue.split("=")[0]
            sanity_issue_histogram[key] = sanity_issue_histogram.get(key, 0) + 1

        oldest = report["oldest_window"]
        oldest_rows_total += int(oldest["row_count"])

        for column in EXPECTED_COLUMNS | {"year"}:
            if column in available or column == "year":
                oldest_observed_value_totals[column] = (
                    oldest_observed_value_totals.get(column, 0) + int(oldest["row_count"])
                )

        for column, count in oldest["missing_values"].items():
            oldest_missing_value_totals[column] = oldest_missing_value_totals.get(column, 0) + int(count)

        oldest_issues = oldest["sanity_checks"]["issues"]
        if oldest_issues:
            oldest_sanity_companies_with_issues += 1
        oldest_sanity_total_issues += int(oldest["sanity_checks"]["issue_count"])
        for issue in oldest_issues:
            key = issue.split("=")[0]
            oldest_sanity_issue_histogram[key] = oldest_sanity_issue_histogram.get(key, 0) + 1

        yearly = report["yearly_problems"]
        for year in yearly["problem_years"]:
            problem_year_company_counts[year] = problem_year_company_counts.get(year, 0) + 1
            detail = yearly["by_year"][year]
            problem_flag_count = len(detail["missing_columns"]) + len(detail["sanity_flags"])
            problem_year_flag_counts[year] = problem_year_flag_counts.get(year, 0) + problem_flag_count

    missing_rates: dict[str, float] = {}
    for column, missing_total in missing_value_totals.items():
        observed_total = observed_value_totals.get(column, 0)
        if observed_total > 0:
            missing_rates[column] = missing_total / observed_total

    oldest_missing_rates: dict[str, float] = {}
    for column, missing_total in oldest_missing_value_totals.items():
        observed_total = oldest_observed_value_totals.get(column, 0)
        if observed_total > 0:
            oldest_missing_rates[column] = missing_total / observed_total

    return {
        "files_audited": files_audited,
        "rows_total": rows_total,
        "historical_years_min": min(years) if years else 0,
        "historical_years_max": max(years) if years else 0,
        "historical_years_avg": (sum(years) / len(years)) if years else 0.0,
        "full_required_columns_companies": full_required,
        "missing_required_counts": missing_required_counts,
        "missing_optional_counts": missing_optional_counts,
        "missing_value_totals": missing_value_totals,
        "missing_value_rates": missing_rates,
        "sanity_companies_with_issues": sanity_companies_with_issues,
        "sanity_total_issues": sanity_total_issues,
        "sanity_issue_histogram": sanity_issue_histogram,
        "oldest_rows_total": oldest_rows_total,
        "oldest_missing_value_totals": oldest_missing_value_totals,
        "oldest_missing_value_rates": oldest_missing_rates,
        "oldest_sanity_companies_with_issues": oldest_sanity_companies_with_issues,
        "oldest_sanity_total_issues": oldest_sanity_total_issues,
        "oldest_sanity_issue_histogram": oldest_sanity_issue_histogram,
        "problem_year_company_counts": dict(sorted(problem_year_company_counts.items())),
        "problem_year_flag_counts": dict(sorted(problem_year_flag_counts.items())),
    }


def format_bulk_report(reports: list[dict[str, Any]]) -> str:
    universe = _aggregate_universe_summary(reports)

    lines = [
        "==========================================",
        "CompaniesMarketCap Historical Financials Audit",
        "==========================================",
        "",
        f"Files audited             {universe['files_audited']}",
        "",
        "Universe summary",
        "----------------",
        f"Total rows                {universe['rows_total']}",
        f"Historical years (min/max) {universe['historical_years_min']}/{universe['historical_years_max']}",
        f"Historical years (avg)    {universe['historical_years_avg']:.2f}",
        (
            "Companies with all required columns "
            f"{universe['full_required_columns_companies']}/{universe['files_audited']}"
        ),
        (
            "Companies with sanity issues "
            f"{universe['sanity_companies_with_issues']}/{universe['files_audited']}"
        ),
        f"Total sanity issue flags  {universe['sanity_total_issues']}",
        "",
        "Required columns missing by company count",
        "-----------------------------------------",
    ]

    for column in sorted(universe["missing_required_counts"]):
        lines.append(
            f"{column:<25} {universe['missing_required_counts'][column]}"
        )

    lines.extend(["", "Optional columns missing by company count", "-----------------------------------------"])
    for column in sorted(universe["missing_optional_counts"]):
        lines.append(
            f"{column:<25} {universe['missing_optional_counts'][column]}"
        )

    lines.extend(["", "Missing value rates across universe", "-----------------------------------"])
    for column in sorted(universe["missing_value_rates"]):
        missing_total = universe["missing_value_totals"].get(column, 0)
        missing_rate = universe["missing_value_rates"][column] * 100
        lines.append(f"{column:<25} {missing_total:>4} missing ({missing_rate:5.1f}%)")

    lines.extend(["", "Sanity issue type counts", "------------------------"])
    if universe["sanity_issue_histogram"]:
        for key in sorted(universe["sanity_issue_histogram"]):
            lines.append(f"{key:<35} {universe['sanity_issue_histogram'][key]}")
    else:
        lines.append("None")

    lines.extend([
        "",
        f"Oldest years focus (first up to {OLDEST_WINDOW_YEARS} per company)",
        "-----------------------------------------------",
        f"Oldest-window rows total     {universe['oldest_rows_total']}",
        (
            "Companies with oldest-window sanity issues "
            f"{universe['oldest_sanity_companies_with_issues']}/{universe['files_audited']}"
        ),
        f"Oldest-window issue flags    {universe['oldest_sanity_total_issues']}",
        "",
        "Oldest-window missing value rates",
        "---------------------------------",
    ])

    for column in sorted(universe["oldest_missing_value_rates"]):
        missing_total = universe["oldest_missing_value_totals"].get(column, 0)
        missing_rate = universe["oldest_missing_value_rates"][column] * 100
        lines.append(f"{column:<25} {missing_total:>4} missing ({missing_rate:5.1f}%)")

    lines.extend(["", "Oldest-window sanity issue type counts", "-------------------------------------"])
    if universe["oldest_sanity_issue_histogram"]:
        for key in sorted(universe["oldest_sanity_issue_histogram"]):
            lines.append(f"{key:<35} {universe['oldest_sanity_issue_histogram'][key]}")
    else:
        lines.append("None")

    lines.extend(["", "Problem years across universe", "-----------------------------"])
    if universe["problem_year_company_counts"]:
        lines.append("Year  companies  issue_flags")
        for year in sorted(universe["problem_year_company_counts"]):
            companies = universe["problem_year_company_counts"][year]
            flags = universe["problem_year_flag_counts"].get(year, 0)
            lines.append(f"{year:<5} {companies:>9} {flags:>11}")
    else:
        lines.append("None")

    lines.extend([
        "",
        "Per-company summary",
        "-------------------",
    ])

    for report in reports:
        lines.append(
            f"{report['ticker']:<8} years={report['historical_years']:<2} "
            f"range={report['first_year'] or '-'}-{report['last_year'] or '-'} "
            f"available={len(report['available_columns']):<2} "
            f"missing={len(report['missing_columns']):<2} "
            f"sanity={report['sanity_checks']['issue_count']:<2}"
        )

    lines.extend(["", "Detailed reports", "----------------"])

    for idx, report in enumerate(reports, start=1):
        lines.append(f"[{idx}] {report['ticker']} ({report['file']})")
        lines.append(f"  historical_years: {report['historical_years']}")
        lines.append(f"  first_year: {report['first_year'] if report['first_year'] is not None else '-'}")
        lines.append(f"  last_year: {report['last_year'] if report['last_year'] is not None else '-'}")
        lines.append(
            "  available_columns: "
            + (", ".join(report["available_columns"]) if report["available_columns"] else "-")
        )
        lines.append(
            "  missing_columns: "
            + (", ".join(report["missing_columns"]) if report["missing_columns"] else "-")
        )
        lines.append(
            "  extra_columns: "
            + (", ".join(report["extra_columns"]) if report["extra_columns"] else "-")
        )
        lines.append("  missing_values:")
        for column in sorted(report["missing_values"]):
            lines.append(f"    - {column}: {report['missing_values'][column]}")
        lines.append("  sanity_issues:")
        if report["sanity_checks"]["issues"]:
            for issue in report["sanity_checks"]["issues"]:
                lines.append(f"    - {issue}")
        else:
            lines.append("    - none")
        oldest = report["oldest_window"]
        oldest_label = "-"
        if oldest["years"]:
            oldest_label = f"{oldest['years'][0]}-{oldest['years'][-1]}"
        lines.append(f"  oldest_window_years: {oldest_label}")
        lines.append("  oldest_window_missing_values:")
        for column in sorted(oldest["missing_values"]):
            lines.append(f"    - {column}: {oldest['missing_values'][column]}")
        lines.append("  oldest_window_sanity_issues:")
        if oldest["sanity_checks"]["issues"]:
            for issue in oldest["sanity_checks"]["issues"]:
                lines.append(f"    - {issue}")
        else:
            lines.append("    - none")
        yearly = report["yearly_problems"]
        lines.append("  yearly_problem_map:")
        if yearly["problem_years"]:
            for year in yearly["problem_years"]:
                details = yearly["by_year"][year]
                lines.append(f"    - year: {year}")
                lines.append(
                    "      missing_columns: "
                    + (", ".join(details["missing_columns"]) if details["missing_columns"] else "-")
                )
                lines.append(
                    "      missing_required_columns: "
                    + (
                        ", ".join(details["missing_required_columns"])
                        if details["missing_required_columns"]
                        else "-"
                    )
                )
                lines.append(
                    "      sanity_flags: "
                    + (", ".join(details["sanity_flags"]) if details["sanity_flags"] else "-")
                )
        else:
            lines.append("    - none")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def audit_universe(data_dir: Path, output_path: Path) -> Path:
    csv_files = sorted(data_dir.glob("*_financials.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No financials CSV files found in {data_dir}")

    reports = [audit_file(path, ticker=_extract_ticker(path)) for path in csv_files]
    content = format_bulk_report(reports)
    print(content, end="")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def audit_single_ticker(data_dir: Path, ticker: str) -> dict[str, Any]:
    candidates = sorted(data_dir.glob(f"{ticker.lower()}_*_financials.csv"))
    if not candidates:
        raise FileNotFoundError(f"No CompaniesMarketCap financials CSV found for ticker: {ticker}")
    return audit_file(candidates[0], ticker=ticker.upper())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit CompaniesMarketCap historical financials CSV files"
    )
    parser.add_argument("ticker", nargs="?", help="Ticker symbol to audit")
    parser.add_argument("--bulk", action="store_true", help="Audit all financials CSV files")
    parser.add_argument("--output", help="Optional path to save the bulk audit report")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    data_dir = repo_root / "data" / "qvm" / "companiesmarketcap"

    if args.bulk:
        default_output = repo_root / "data" / "qvm" / "historical_financials_audit.txt"
        output_path = Path(args.output) if args.output else default_output
        written_path = audit_universe(data_dir, output_path)
        print(f"Saved bulk audit report to {written_path}")
        return

    if not args.ticker:
        raise SystemExit("Provide a ticker symbol or use --bulk")

    report = audit_single_ticker(data_dir, args.ticker)
    print(format_company_report(report))


if __name__ == "__main__":
    main()
