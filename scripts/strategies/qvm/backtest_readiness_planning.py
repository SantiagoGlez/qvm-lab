#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

import pandas as pd


QUALITY_METRICS = [
    "revenue_cagr_3y",
    "eps_cagr_3y",
    "roe",
    "operating_margin",
    "net_debt",
    "debt_to_equity",
    "share_count_cagr_3y",
]

QUALITY_LABELS = {
    "revenue_cagr_3y": "Revenue CAGR (3Y)",
    "eps_cagr_3y": "EPS CAGR (3Y)",
    "roe": "ROE",
    "operating_margin": "Operating Margin",
    "net_debt": "Net Debt",
    "debt_to_equity": "Debt / Equity",
    "share_count_cagr_3y": "Share Count CAGR",
}


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _has_year_value(df: pd.DataFrame, year: int, column: str) -> bool:
    row = df[df["year"] == year]
    if row.empty or column not in row.columns:
        return False
    value = _to_numeric(row[column]).iloc[0]
    return pd.notna(value)


def _get_year_value(df: pd.DataFrame, year: int, column: str) -> float | None:
    row = df[df["year"] == year]
    if row.empty or column not in row.columns:
        return None
    value = _to_numeric(row[column]).iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _can_compute_cagr_3y(df: pd.DataFrame, year: int, column: str) -> bool:
    current = _get_year_value(df, year, column)
    past = _get_year_value(df, year - 3, column)
    if current is None or past is None:
        return False
    # CAGR with non-positive endpoints is unstable/non-real for planning purposes.
    return current > 0 and past > 0


def _can_compute_roe(df: pd.DataFrame, year: int) -> bool:
    net_income = _get_year_value(df, year, "net_income")
    equity = _get_year_value(df, year, "net_assets")
    if net_income is None or equity is None:
        return False
    return equity != 0


def _can_compute_operating_margin(df: pd.DataFrame, year: int) -> bool:
    return _has_year_value(df, year, "operating_margin")


def _can_compute_net_debt(df: pd.DataFrame, year: int) -> bool:
    debt = _get_year_value(df, year, "total_debt")
    cash = _get_year_value(df, year, "cash")
    return debt is not None and cash is not None


def _can_compute_debt_to_equity(df: pd.DataFrame, year: int) -> bool:
    debt = _get_year_value(df, year, "total_debt")
    equity = _get_year_value(df, year, "net_assets")
    if debt is None or equity is None:
        return False
    return equity != 0


def _can_compute_revenue_cagr_3y(df: pd.DataFrame, year: int) -> bool:
    return _can_compute_cagr_3y(df, year, "revenue")


def _can_compute_eps_cagr_3y(df: pd.DataFrame, year: int) -> bool:
    return _can_compute_cagr_3y(df, year, "eps")


def _can_compute_share_count_cagr_3y(df: pd.DataFrame, year: int) -> bool:
    return _can_compute_cagr_3y(df, year, "shares_outstanding")


def _valuation_coverage(df: pd.DataFrame, year: int, lookback_years: int) -> float:
    start_year = year - lookback_years + 1
    expected_years = list(range(start_year, year + 1))
    if not expected_years:
        return 0.0

    coverage_hits = 0
    for check_year in expected_years:
        if _has_year_value(df, check_year, "pe_ratio"):
            coverage_hits += 1

    return (coverage_hits / len(expected_years)) * 100


def _historical_pe_observations(df: pd.DataFrame, year: int) -> int:
    if "pe_ratio" not in df.columns:
        return 0
    mask = (df["year"] <= year) & df["pe_ratio"].notna()
    return int(mask.sum())


def _prepare_frame(df: pd.DataFrame, numeric_columns: set[str]) -> pd.DataFrame | None:
    df.columns = [column.strip().lower() for column in df.columns]

    if "year" not in df.columns:
        return None

    df["year"] = _to_numeric(df["year"])
    df = df[df["year"].notna()].copy()
    if df.empty:
        return None
    df["year"] = df["year"].astype(int)

    for column in numeric_columns:
        if column in df.columns:
            df[column] = _to_numeric(df[column])

    return df


def _load_financial_frames(data_dir: Path) -> list[tuple[str, pd.DataFrame]]:
    frames: list[tuple[str, pd.DataFrame]] = []
    for path in sorted(data_dir.glob("*_financials.csv")):
        ticker = path.stem.split("_")[0].upper()
        df = pd.read_csv(path)

        prepared = _prepare_frame(
            df,
            {
            "revenue",
            "eps",
            "net_income",
            "operating_margin",
            "cash",
            "total_debt",
            "total_assets",
            "net_assets",
            "pe_ratio",
            "shares_outstanding",
            },
        )
        if prepared is None:
            continue

        frames.append((ticker, prepared))

    return frames


def _load_valuation_frames(data_dir: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for path in sorted(data_dir.glob("*_valuation.csv")):
        ticker = path.stem.split("_")[0].upper()
        df = pd.read_csv(path)
        prepared = _prepare_frame(
            df,
            {
                "pe_ratio",
                "revenue",
                "net_income",
                "cash",
                "total_assets",
                "dividend_yield",
            },
        )
        if prepared is None:
            continue
        frames[ticker] = prepared
    return frames


def build_planning_tables(
    company_frames: list[tuple[str, pd.DataFrame]],
    valuation_frames: dict[str, pd.DataFrame],
    valuation_source: str,
    start_year: int,
    end_year: int,
    valuation_lookback_years: int,
    quality_threshold_pct: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rules: dict[str, Callable[[pd.DataFrame, int], bool]] = {
        "revenue_cagr_3y": _can_compute_revenue_cagr_3y,
        "eps_cagr_3y": _can_compute_eps_cagr_3y,
        "roe": _can_compute_roe,
        "operating_margin": _can_compute_operating_margin,
        "net_debt": _can_compute_net_debt,
        "debt_to_equity": _can_compute_debt_to_equity,
        "share_count_cagr_3y": _can_compute_share_count_cagr_3y,
    }

    years = list(range(start_year, end_year + 1))
    company_count = len(company_frames)

    planning_rows: list[dict[str, float | int]] = []
    per_metric_rows: list[dict[str, float | int]] = []

    for formation_year in years:
        valuation_coverages: list[float] = []
        pe_observation_counts: list[int] = []
        quality_coverages: list[float] = []
        metric_available_counts = {metric: 0 for metric in QUALITY_METRICS}

        usable_companies = 0

        for ticker, df in company_frames:
            valuation_df = df
            if valuation_source == "valuation-files":
                valuation_df = valuation_frames.get(ticker, df)

            valuation_cov = _valuation_coverage(valuation_df, formation_year, valuation_lookback_years)
            valuation_coverages.append(valuation_cov)
            pe_observation_counts.append(_historical_pe_observations(valuation_df, formation_year))

            available_metric_count = 0
            for metric in QUALITY_METRICS:
                if metric_rules[metric](df, formation_year):
                    available_metric_count += 1
                    metric_available_counts[metric] += 1

            quality_cov = (available_metric_count / len(QUALITY_METRICS)) * 100
            quality_coverages.append(quality_cov)

            if quality_cov >= quality_threshold_pct:
                usable_companies += 1

        planning_rows.append(
            {
                "Formation Year": formation_year,
                    "Avg Historical PE Observations": round(sum(pe_observation_counts) / company_count, 1)
                    if company_count
                    else 0.0,
                "Average Valuation Coverage (%)": round(sum(valuation_coverages) / company_count, 1)
                if company_count
                else 0.0,
                "Average Quality Coverage (%)": round(sum(quality_coverages) / company_count, 1)
                if company_count
                else 0.0,
                "Companies Usable (Quality >= 75%)": usable_companies,
            }
        )

        metric_row: dict[str, float | int] = {"Formation Year": formation_year}
        for metric in QUALITY_METRICS:
            pct = (metric_available_counts[metric] / company_count) * 100 if company_count else 0.0
            metric_row[QUALITY_LABELS[metric]] = round(pct, 1)
        per_metric_rows.append(metric_row)

    planning_table = pd.DataFrame(planning_rows)
    per_metric_table = pd.DataFrame(per_metric_rows)
    return planning_table, per_metric_table


def _format_table(df: pd.DataFrame) -> str:
    return df.to_string(index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate backtest readiness planning tables from historical financials data"
    )
    parser.add_argument("--start-year", type=int, default=2012, help="First formation year")
    parser.add_argument("--end-year", type=int, default=2025, help="Last formation year")
    parser.add_argument(
        "--valuation-lookback-years",
        type=int,
        default=10,
        help="Required valuation lookback window length used for coverage",
    )
    parser.add_argument(
        "--valuation-source",
        choices=["valuation-files", "financials"],
        default="valuation-files",
        help="Dataset used for valuation coverage (pe_ratio)",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=75.0,
        help="Minimum quality coverage percentage to count a company as usable",
    )
    parser.add_argument(
        "--output",
        default="data/qvm/backtest/backtest_readiness_planning.txt",
        help="Output text report path",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    data_dir = repo_root / "data" / "qvm" / "companiesmarketcap"

    company_frames = _load_financial_frames(data_dir)
    if not company_frames:
        raise FileNotFoundError(f"No *_financials.csv files found in {data_dir}")

    valuation_frames = _load_valuation_frames(data_dir)

    planning_table, per_metric_table = build_planning_tables(
        company_frames=company_frames,
        valuation_frames=valuation_frames,
        valuation_source=args.valuation_source,
        start_year=args.start_year,
        end_year=args.end_year,
        valuation_lookback_years=args.valuation_lookback_years,
        quality_threshold_pct=args.quality_threshold,
    )

    lines = [
        "===========================================",
        "Historical Backtest Readiness Planning",
        "===========================================",
        "",
        (
            f"Assumptions: valuation coverage uses {args.valuation_lookback_years}Y PE window "
            f"from {args.valuation_source}; "
            f"company usable threshold = quality coverage >= {args.quality_threshold:.1f}%"
        ),
        "",
        "Planning Table",
        "--------------",
        _format_table(planning_table),
        "",
        "Historical Metric Availability by Formation Year (%)",
        "----------------------------------------------------",
        _format_table(per_metric_table),
        "",
    ]
    report_text = "\n".join(lines)

    output_path = (repo_root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")

    planning_csv = output_path.with_name("backtest_readiness_planning_table.csv")
    metric_csv = output_path.with_name("backtest_readiness_metric_availability.csv")
    planning_table.to_csv(planning_csv, index=False)
    per_metric_table.to_csv(metric_csv, index=False)

    print(report_text, end="")
    print(f"Saved planning report to {output_path}")
    print(f"Saved planning table CSV to {planning_csv}")
    print(f"Saved metric availability CSV to {metric_csv}")


if __name__ == "__main__":
    main()
