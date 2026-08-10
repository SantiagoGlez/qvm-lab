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


def audit_file(path: Path | str, ticker: str | None = None) -> dict[str, Any]:
    csv_path = Path(path)
    df = read_financials_csv(csv_path)

    presence = _column_presence(df)
    year_profile = _year_profile(df)
    missing_counts = _missing_value_counts(df, ["year"] + presence["available"])
    sanity_checks = _build_sanity_checks(df, year_profile)

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

    missing_rates: dict[str, float] = {}
    for column, missing_total in missing_value_totals.items():
        observed_total = observed_value_totals.get(column, 0)
        if observed_total > 0:
            missing_rates[column] = missing_total / observed_total

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
