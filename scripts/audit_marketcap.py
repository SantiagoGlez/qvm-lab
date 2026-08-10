#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {"Year", "revenue", "net_income", "pe_ratio", "cash", "total_assets"}
OPTIONAL_COLUMNS = {"dividend_yield"}


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    available_columns = set(df.columns)
    missing = REQUIRED_COLUMNS - available_columns
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    df = df.copy()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    for column in ["revenue", "net_income", "pe_ratio", "cash", "total_assets"]:
        df[column] = _coerce_numeric(df[column])
    if "dividend_yield" in available_columns:
        df["dividend_yield"] = _coerce_numeric(df["dividend_yield"])
    else:
        df["dividend_yield"] = pd.Series([float("nan")] * len(df), dtype="float64")
    return df


def _year_stats(df: pd.DataFrame) -> dict[str, Any]:
    years = df["Year"].dropna().astype(int).tolist()
    if not years:
        return {"rows": len(df), "years": (None, None), "duplicates": 0, "sorted": True}

    unique_years = sorted(set(years))
    duplicate_years = len(years) - len(unique_years)
    sorted_years = years == sorted(years)
    return {
        "rows": len(df),
        "years": (min(unique_years), max(unique_years)),
        "duplicates": duplicate_years,
        "sorted": sorted_years,
    }


def _missing_counts(df: pd.DataFrame) -> dict[str, int]:
    return {column: int(df[column].isna().sum()) for column in ["revenue", "net_income", "pe_ratio", "cash", "total_assets", "dividend_yield"]}


def _pe_history(df: pd.DataFrame) -> dict[str, int]:
    pe_values = df["pe_ratio"]
    valid = int(pe_values.notna().sum())
    missing = int(pe_values.isna().sum())
    negative = int((pe_values.notna() & (pe_values < 0)).sum())
    zero = int((pe_values.notna() & (pe_values == 0)).sum())
    return {"valid": valid, "missing": missing, "negative": negative, "zero": zero}


def _revenue_stats(df: pd.DataFrame) -> dict[str, int]:
    revenue = df["revenue"]
    return {
        "negative": int((revenue.notna() & (revenue < 0)).sum()),
        "zero": int((revenue.notna() & (revenue == 0)).sum()),
    }


def _net_income_stats(df: pd.DataFrame) -> dict[str, int]:
    net_income = df["net_income"]
    return {
        "missing": int(net_income.isna().sum()),
        "negative": int((net_income.notna() & (net_income < 0)).sum()),
    }


def _year_coverage(df: pd.DataFrame) -> dict[str, Any]:
    years = sorted({int(v) for v in df["Year"].dropna().astype(int).tolist()})
    gaps = []
    for previous, current in zip(years, years[1:]):
        if current - previous > 1:
            gaps.append((previous, current))
    return {"gaps": gaps, "count": len(years)}


def _recent_window(df: pd.DataFrame, years_back: int = 15) -> dict[str, Any]:
    years = sorted({int(v) for v in df["Year"].dropna().astype(int).tolist()})
    if not years:
        return {"start": None, "end": None, "pe_missing": 0, "pe_valid": 0, "net_income_missing": 0, "pe_missing_years": [], "net_income_missing_years": []}

    end_year = max(years)
    start_year = end_year - years_back + 1
    recent_mask = df["Year"].isin([year for year in years if year >= start_year])
    recent_df = df.loc[recent_mask]

    pe_series = recent_df["pe_ratio"]
    net_income_series = recent_df["net_income"]

    return {
        "start": start_year,
        "end": end_year,
        "pe_missing": int(pe_series.isna().sum()),
        "pe_valid": int(pe_series.notna().sum()),
        "net_income_missing": int(net_income_series.isna().sum()),
        "pe_missing_years": [int(year) for year in sorted(recent_df["Year"].dropna().astype(int).tolist()) if pd.isna(recent_df.loc[recent_df["Year"].astype(int) == year, "pe_ratio"].iloc[0])],
        "net_income_missing_years": [int(year) for year in sorted(recent_df["Year"].dropna().astype(int).tolist()) if pd.isna(recent_df.loc[recent_df["Year"].astype(int) == year, "net_income"].iloc[0])],
    }


def _filtering_stats(df: pd.DataFrame) -> dict[str, int]:
    pe_values = df["pe_ratio"].dropna()
    raw = int(pe_values.shape[0])
    if raw == 0:
        return {"raw_pe": 0, "outliers_removed": 0, "used": 0}

    q1 = pe_values.quantile(0.25)
    q3 = pe_values.quantile(0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return {"raw_pe": raw, "outliers_removed": 0, "used": raw}

    max_allowed = q3 + 3 * iqr
    filtered = pe_values[pe_values <= max_allowed]
    outliers_removed = raw - int(filtered.shape[0])
    return {"raw_pe": raw, "outliers_removed": outliers_removed, "used": int(filtered.shape[0])}


def audit_file(path: Path | str, ticker: str | None = None) -> dict[str, Any]:
    csv_path = Path(path)
    df = read_csv(csv_path)
    year_stats = _year_stats(df)
    missing_values = _missing_counts(df)
    pe_history = _pe_history(df)
    revenue_stats = _revenue_stats(df)
    net_income_stats = _net_income_stats(df)
    coverage = _year_coverage(df)
    filtering = _filtering_stats(df)
    recent_window = _recent_window(df)

    return {
        "ticker": ticker or csv_path.stem.replace("_valuation", "").upper(),
        "rows": year_stats["rows"],
        "years": year_stats["years"],
        "duplicates": year_stats["duplicates"],
        "years_sorted": year_stats["sorted"],
        "missing_values": missing_values,
        "pe_history": pe_history,
        "revenue": revenue_stats,
        "net_income": net_income_stats,
        "year_coverage": coverage,
        "filtering": filtering,
        "recent_window": recent_window,
    }


def classify_confidence(report: dict[str, Any]) -> str:
    warnings = 0
    recent_window = report["recent_window"]
    coverage = report["year_coverage"]

    pe_history = report["pe_history"]
    if recent_window["pe_valid"] < 10:
        warnings += 1
    if recent_window["pe_missing"] / max(recent_window["pe_valid"] + recent_window["pe_missing"], 1) > 0.25:
        warnings += 1
    if pe_history["negative"] / max(pe_history["valid"], 1) > 0.30:
        warnings += 1

    revenue = report["revenue"]
    if revenue["negative"] > 0:
        warnings += 1
    if revenue["zero"] > 0:
        warnings += 1

    net_income = report["net_income"]
    if recent_window["net_income_missing"] > 0:
        warnings += 1
    if net_income["negative"] > 0:
        warnings += 1

    if any(start <= recent_window["end"] and end >= recent_window["start"] for start, end in coverage["gaps"]):
        warnings += 1
    if coverage["count"] < 10:
        warnings += 1

    if warnings == 0:
        return "HIGH"
    if warnings <= 2:
        return "MEDIUM"
    return "LOW"


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "=========================",
        "CompaniesMarketCap Audit",
        "=========================",
        "",
        f"Ticker              {report['ticker']}",
        "",
        "Dataset",
        "-------",
        f"Rows                {report['rows']}",
        f"Years               {report['years'][0]}-{report['years'][1]}" if report['years'][0] is not None else "Years               -",
        f"Duplicates          {report['duplicates']}",
        "",
        "PE History",
        "----------",
        f"Valid               {report['pe_history']['valid']}",
        f"Missing             {report['pe_history']['missing']}",
        f"Negative            {report['pe_history']['negative']}",
        f"Zero                {report['pe_history']['zero']}",
        "",
        "Revenue",
        "-------",
        f"Missing             {report['missing_values']['revenue']}",
        "",
        "Net Income",
        "----------",
        f"Missing             {report['net_income']['missing']}",
        f"Negative            {report['net_income']['negative']}",
        "",
        "Filtering",
        "---------",
        f"Raw PE              {report['filtering']['raw_pe']}",
        f"Outliers Removed    {report['filtering']['outliers_removed']}",
        f"Used                {report['filtering']['used']}",
        "",
        "Warnings",
        "--------",
    ]

    warnings: list[str] = []
    recent_window = report["recent_window"]
    pe_history = report["pe_history"]
    if recent_window["pe_missing"] > 0:
        warnings.append(f"⚠ {recent_window['pe_missing']} missing PE observations in the recent {recent_window['start']}-{recent_window['end']} window")
    if pe_history["negative"] / max(pe_history["valid"], 1) > 0.30:
        warnings.append(f"⚠ {pe_history['negative']} negative PE observations")
    if recent_window["pe_valid"] < 10:
        warnings.append("⚠ fewer than 10 valid PE observations in the recent window")

    revenue = report["revenue"]
    if revenue["negative"] > 0:
        warnings.append("⚠ negative revenue values")
    if revenue["zero"] > 0:
        warnings.append("⚠ zero revenue values")

    net_income = report["net_income"]
    if recent_window["net_income_missing"] > 0:
        warnings.append(f"⚠ {recent_window['net_income_missing']} missing net income values in the recent window")

    if any(start <= recent_window["end"] and end >= recent_window["start"] for start, end in report["year_coverage"]["gaps"]):
        warnings.append("⚠ gaps larger than one year in the recent history window")
    if report["year_coverage"]["count"] < 10:
        warnings.append("⚠ fewer than 10 historical years")

    lines.extend(warnings if warnings else ["None"])
    lines.extend(["", "Confidence", "----------", classify_confidence(report)])
    return "\n".join(lines)


def audit_directory(data_dir: Path | str, output_path: Path | str | None = None) -> Path | None:
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_path}")

    csv_files = sorted(data_path.glob("*_valuation.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No valuation CSV files found in {data_path}")

    reports = []
    for csv_path in csv_files:
        ticker = csv_path.stem.replace("_valuation", "").split("_")[0].upper()
        reports.append(audit_file(csv_path, ticker=ticker))

    lines = [
        "=========================",
        "CompaniesMarketCap Audit",
        "=========================",
        "",
        f"Files audited        {len(reports)}",
        "",
    ]

    for report in reports:
        lines.append(f"Ticker              {report['ticker']}")
        lines.append(f"Rows                {report['rows']}")
        lines.append(f"Confidence          {classify_confidence(report)}")
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    print(content, end="")

    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(content, encoding="utf-8")
        return output_file

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit CompaniesMarketCap valuation CSV files")
    parser.add_argument("ticker", nargs="?", help="Ticker symbol to audit")
    parser.add_argument("--bulk", action="store_true", help="Audit all valuation CSV files in the data directory")
    parser.add_argument("--output", help="Optional path to save the audit report")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "data" / "qvm" / "companiesmarketcap"

    if args.bulk:
        output_path = Path(args.output) if args.output else None
        audit_directory(data_dir, output_path=output_path)
        return

    if not args.ticker:
        raise SystemExit("Provide a ticker symbol or use --bulk")

    candidates = sorted(data_dir.glob(f"{args.ticker.lower()}_*_valuation.csv"))
    if not candidates:
        raise SystemExit(f"No CompaniesMarketCap valuation CSV found for ticker: {args.ticker}")

    report = audit_file(candidates[0], ticker=args.ticker.upper())
    print(format_report(report))


if __name__ == "__main__":
    main()
