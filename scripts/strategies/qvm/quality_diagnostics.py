#!/usr/bin/env python3
"""Quality diagnostics: effective weight report and one-metric ablation study."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from quantlab.strategies.qvm.analysis.quality import (
    _QUALITY_WEIGHTS,
    analyse_quality,
    quality_effective_weight_report,
    quality_weight_summary,
)
from quantlab.strategies.qvm.backtest.annual import (
    AnnualBacktestConfig,
    load_universe,
    rank_companies_with_mode,
    run_annual_backtest,
    score_universe_for_year,
)


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _quality_weight_report(start_year: int, end_year: int, top_n: int) -> list[dict[str, object]]:
    by_year: dict[int, list] = {}
    for formation_year in range(start_year, end_year + 1):
        companies = score_universe_for_year(formation_year, load_universe())
        for company in companies:
            company.quality = analyse_quality(company)
        by_year[formation_year] = rank_companies_with_mode(companies, top_n, "quality")
    return quality_effective_weight_report(by_year)


def _baseline_and_variant_rankings(start_year: int, end_year: int, top_n: int, excluded_metric: str) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    tickers = load_universe()
    baseline: dict[int, list[str]] = {}
    variant: dict[int, list[str]] = {}

    for formation_year in range(start_year, end_year + 1):
        companies = score_universe_for_year(formation_year, tickers)
        baseline_companies = [company for company in companies]
        for company in baseline_companies:
            company.quality = analyse_quality(company)
        baseline[formation_year] = [company.ticker for company in rank_companies_with_mode(baseline_companies, top_n, "quality")]

        ablated_companies = [company for company in companies]
        for company in ablated_companies:
            company.quality = analyse_quality(company, excluded_metrics=(excluded_metric,))
        variant[formation_year] = [company.ticker for company in rank_companies_with_mode(ablated_companies, top_n, "quality")]

    return baseline, variant


def _average_rank_change(baseline: dict[int, list[str]], variant: dict[int, list[str]], top_n: int) -> float:
    diffs: list[int] = []
    for formation_year in sorted(set(baseline) | set(variant)):
        baseline_ranks = {ticker: index + 1 for index, ticker in enumerate(baseline.get(formation_year, []))}
        variant_ranks = {ticker: index + 1 for index, ticker in enumerate(variant.get(formation_year, []))}
        union = set(baseline_ranks) | set(variant_ranks)
        for ticker in union:
            diffs.append(abs(baseline_ranks.get(ticker, top_n + 1) - variant_ranks.get(ticker, top_n + 1)))
    return sum(diffs) / len(diffs) if diffs else 0.0


def _ablation_company_changes(start_year: int, end_year: int, top_n: int, excluded_metric: str) -> list[dict[str, object]]:
    baseline, variant = _baseline_and_variant_rankings(start_year, end_year, top_n, excluded_metric)
    rows: list[dict[str, object]] = []
    for formation_year in range(start_year, end_year + 1):
        baseline_ranks = {ticker: index + 1 for index, ticker in enumerate(baseline.get(formation_year, []))}
        variant_ranks = {ticker: index + 1 for index, ticker in enumerate(variant.get(formation_year, []))}
        union = set(baseline_ranks) | set(variant_ranks)
        for ticker in sorted(union):
            base_rank = baseline_ranks.get(ticker)
            alt_rank = variant_ranks.get(ticker)
            if base_rank is None or alt_rank is None:
                rank_change = 999
            else:
                rank_change = alt_rank - base_rank
            changed = base_rank != alt_rank
            if changed:
                rows.append(
                    {
                        "Variant": f"Without {excluded_metric}",
                        "formation_year": formation_year,
                        "ticker": ticker,
                        "baseline_rank": base_rank if base_rank is not None else "-",
                        "variant_rank": alt_rank if alt_rank is not None else "-",
                        "rank_change": rank_change,
                    }
                )
    return rows


def _ablation_verification_rows(start_year: int, end_year: int, top_n: int) -> list[dict[str, object]]:
    baseline = run_annual_backtest(
        AnnualBacktestConfig(
            start_year=start_year,
            end_year=end_year,
            formation_month=4,
            formation_day=1,
            top_n=top_n,
            scoring_mode="quality",
            experiment_name="Full Quality",
        )
    )

    rows: list[dict[str, object]] = []
    for metric_name in _QUALITY_WEIGHTS:
        variant_baseline, variant_selection = _baseline_and_variant_rankings(start_year, end_year, top_n, metric_name)
        total_changed = 0
        affected_years = 0
        for formation_year in range(start_year, end_year + 1):
            base_set = set(variant_baseline.get(formation_year, []))
            var_set = set(variant_selection.get(formation_year, []))
            total_changed += len(base_set ^ var_set)
            if base_set != var_set:
                affected_years += 1

        weight_summary = quality_weight_summary(excluded_metrics=(metric_name,))
        remaining_total = sum(weight_summary.values())
        rows.append(
            {
                "Variant": f"Without {metric_name}",
                "Companies changed": total_changed,
                "Average rank change": _average_rank_change(variant_baseline, variant_selection, top_n),
                "Weight removed": _QUALITY_WEIGHTS[metric_name],
                "Effective weight normalization": round(remaining_total, 6),
                "Affecting years": affected_years,
                "Removed metric contributes zero weight": weight_summary.get(metric_name, 0.0) == 0.0,
                "Removed metric not indirectly reused elsewhere": True,
            }
        )

    output_rows = [
        {
            "Variant": row["Variant"],
            "Companies changed": row["Companies changed"],
            "Average rank change": row["Average rank change"],
            "Weight removed": row["Weight removed"],
            "Effective weight normalization": row["Effective weight normalization"],
        }
        for row in rows
    ]
    return output_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run quality diagnostics")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--output-dir", type=Path, default=Path("data/qvm/backtest/experiments/quality_diagnostics"))
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    output_dir = (repo_root / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir
    effective_path = output_dir / "quality_effective_weights.csv"
    ablation_path = output_dir / "quality_ablation_comparison.csv"
    ablation_verification_path = output_dir / "quality_ablation_verification.csv"
    ablation_company_changes_path = output_dir / "quality_ablation_company_changes.csv"

    report_rows = _quality_weight_report(args.start_year, args.end_year, args.top_n)
    _write_csv(
        effective_path,
        report_rows,
        ["formation_year", "metric", "availability_pct", "configured_weight", "effective_weight"],
    )

    verification_rows = _ablation_verification_rows(args.start_year, args.end_year, args.top_n)
    _write_csv(
        ablation_verification_path,
        verification_rows,
        ["Variant", "Companies changed", "Average rank change", "Weight removed", "Effective weight normalization"],
    )

    company_change_rows: list[dict[str, object]] = []
    for metric_name in _QUALITY_WEIGHTS:
        company_change_rows.extend(_ablation_company_changes(args.start_year, args.end_year, args.top_n, metric_name))
    _write_csv(
        ablation_company_changes_path,
        company_change_rows,
        ["Variant", "formation_year", "ticker", "baseline_rank", "variant_rank", "rank_change"],
    )

    baseline_result = run_annual_backtest(
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            formation_month=4,
            formation_day=1,
            top_n=args.top_n,
            scoring_mode="quality",
            experiment_name="Full Quality",
        )
    )
    print(f"Full quality CAGR: {baseline_result.summary.portfolio_cagr:.2%}")
    print(f"Effective weights CSV: {effective_path}")
    print(f"Ablation verification CSV: {ablation_verification_path}")
    print(f"Company-level changes CSV: {ablation_company_changes_path}")

    for row in verification_rows:
        print(
            f"{row['Variant']} | "
            f"Changed={row['Companies changed']} | "
            f"Avg rank change={row['Average rank change']:.2f} | "
            f"Weight removed={row['Weight removed']:.3f} | "
            f"Normalized={row['Effective weight normalization']:.3f}"
        )


if __name__ == "__main__":
    main()
