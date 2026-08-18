import argparse
import runpy
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from quantlab.strategies.qvm.backtest.annual import (
    AnnualBacktestConfig,
    build_selection_diagnostics_row,
    load_universe,
    quality_eligible,
    score_universe_for_year,
    select_companies,
    run_annual_backtest,
    run_experiment_suite,
    run_quality_battle_test_suite,
    analyse_quality,
)
from quantlab.strategies.qvm.reports.console import print_report
from quantlab.strategies.qvm.service import analyse_company


def company_cli() -> None:
    """Run QVM analysis for a single ticker and print the full report."""
    parser = argparse.ArgumentParser(description="Run QVM analysis for one ticker")
    parser.add_argument("ticker", help="Ticker symbol to analyze")
    args = parser.parse_args(sys.argv[1:])

    company = analyse_company(args.ticker)
    print_report(company)


def universe_cli() -> None:
    """Run the QVM universe analysis and write results to data/qvm/results.csv."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "strategies" / "qvm" / "update_universe.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Universe script not found: {script_path}")

    sys.path.insert(0, str(repo_root))
    runpy.run_path(str(script_path), run_name="__main__")


def _read_selection_diagnostics_summary(path: Path) -> dict[str, float] | None:
    if not path.exists():
        return None

    frame = pd.read_csv(path)
    if frame.empty:
        return None

    return {
        "years": float(len(frame)),
        "avg_selected_n": float(frame["selected_n"].mean()),
        "avg_universe_n": float(frame["universe_n"].mean()),
        "avg_val_spread": float(frame["val_median_spread"].mean()),
        "avg_quality_spread": float(frame["quality_median_spread"].mean()),
        "avg_coverage_spread": float(frame["coverage_median_spread"].mean()),
    }


def _print_selection_diagnostics_summary(path: Path, prefix: str = "Selection diagnostics") -> None:
    summary = _read_selection_diagnostics_summary(path)
    if summary is None:
        print(f"{prefix} | no rows")
        return

    print(
        f"{prefix} | "
        f"years={int(summary['years'])} | "
        f"avg_selected_n={summary['avg_selected_n']:.2f} | "
        f"avg_universe_n={summary['avg_universe_n']:.2f} | "
        f"avg_val_spread={summary['avg_val_spread']:+.2f} | "
        f"avg_quality_spread={summary['avg_quality_spread']:+.2f} | "
        f"avg_coverage_spread={summary['avg_coverage_spread']:+.3f}"
    )


def backtest_cli() -> None:
    """Run the annual QVM backtest and write audit artifacts."""
    parser = argparse.ArgumentParser(description="Run the annual QVM backtest")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--formation-month", type=int, default=4)
    parser.add_argument("--formation-day", type=int, default=1)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--scoring-mode", type=str, default="qv", choices=["qv", "quality", "valuation"])
    args = parser.parse_args(sys.argv[1:])

    config = AnnualBacktestConfig(
        start_year=args.start_year,
        end_year=args.end_year,
        formation_month=args.formation_month,
        formation_day=args.formation_day,
        top_n=args.top_n,
        output_dir=args.output_dir,
        scoring_mode=args.scoring_mode,
    )
    result = run_annual_backtest(config)

    print(f"Audit CSV: {result.audit_path}")
    print(f"Returns CSV: {result.returns_path}")
    print(f"Selection diagnostics CSV: {result.selection_diagnostics_path}")
    print(
        "Summary | "
        f"years={result.summary.years} | "
        f"portfolio_cagr={result.summary.portfolio_cagr:.2%} | "
        f"benchmark_cagr={result.summary.benchmark_cagr:.2%} | "
        f"win_rate={result.summary.win_rate:.2%}"
    )
    _print_selection_diagnostics_summary(result.selection_diagnostics_path)


def experiments_cli() -> None:
    """Run a set of annual backtest experiments and write a comparison table."""
    parser = argparse.ArgumentParser(description="Run QVM backtest experiment suite")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("data/qvm/backtest/experiments"))
    parser.add_argument(
        "--experiment",
        type=str,
        default=None,
        help="Run a single experiment by exact name; defaults to all experiments.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append the selected experiment rows to an existing comparison CSV instead of overwriting it.",
    )
    args = parser.parse_args(sys.argv[1:])

    configs = [
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="valuation",
            experiment_name="Valuation Only Apr-01",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            experiment_name="Quality Only Apr-01",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="qv",
            experiment_name="QV Baseline Apr-01",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=1,
            formation_day=2,
            scoring_mode="qv",
            experiment_name="QV Jan Rebalance",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=1,
            formation_day=2,
            scoring_mode="quality",
            experiment_name="Quality Only Jan Rebalance",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_soft_valuation_guard",
            quality_pool_size=20,
            valuation_guard_min_score=20.0,
            experiment_name="Quality + Soft Valuation Guard (>=20)",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_soft_valuation_guard",
            quality_pool_size=20,
            valuation_guard_min_score=30.0,
            experiment_name="Quality + Soft Valuation Guard (>=30)",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_soft_valuation_guard",
            quality_pool_size=20,
            valuation_guard_min_score=40.0,
            experiment_name="Quality + Soft Valuation Guard (>=40)",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_cheapest_half",
            quality_pool_size=20,
            experiment_name="Quality -> Cheapest Half",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_hysteresis",
            quality_hysteresis_keep_top_n=15,
            quality_hysteresis_min_gap=2.0,
            experiment_name="Quality + Hold Buffer (Top15, 2pt)",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="portfolio_signal",
            experiment_name="Quality + Buy/Hold Signals",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="action_simplified_strict_band",
            experiment_name="Action Simplified: Overall>=80 + Fair/Cheap/Deep",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="action_simplified_relaxed_band",
            experiment_name="Action Simplified: Overall>=80 + Not Very Expensive",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="action_simplified_relaxed_score_band",
            experiment_name="Action Simplified: Overall>=75 + Not Very Expensive",
        ),
    ]

    if args.experiment is not None:
        selected_name = args.experiment.strip()
        configs = [config for config in configs if config.experiment_name == selected_name]
        if not configs:
            raise ValueError(f"Experiment not found: {selected_name}")

    comparison_path = args.output_dir / "experiment_comparison.csv"
    if args.append and comparison_path.exists():
        temp_dir = args.output_dir / ".tmp_append_single_experiment"
        temp_dir.mkdir(parents=True, exist_ok=True)
        suite = run_experiment_suite(configs=configs, output_dir=temp_dir)
        temp_csv = temp_dir / "experiment_comparison.csv"
        existing = pd.read_csv(comparison_path)
        new_rows = pd.read_csv(temp_csv).to_dict(orient="records")
        for new_row in new_rows:
            existing = existing[existing["experiment"] != new_row["experiment"]]
        combined = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
        combined.to_csv(comparison_path, index=False)
        print(f"Appended {len(new_rows)} row(s) to {comparison_path}")
    else:
        suite = run_experiment_suite(configs=configs, output_dir=args.output_dir)
        print(f"Comparison CSV: {suite.comparison_path}")

    for row in suite.rows:
        print(
            f"{row.experiment} | "
            f"CAGR={row.cagr:.2%} | "
            f"Sharpe={row.sharpe:.2f} | "
            f"MaxDD={row.max_drawdown:.2%} | "
            f"Turnover={row.turnover:.2%} | "
            f"WinRate={row.win_rate_vs_spy:.2%}"
        )
        run_result = suite.run_results.get(row.experiment)
        if run_result is not None:
            _print_selection_diagnostics_summary(
                run_result.selection_diagnostics_path,
                prefix=f"{row.experiment} diagnostics",
            )


def quality_battletest_cli() -> None:
    """Run quality-only one-factor-at-a-time battle tests plus leave-one-year-out."""
    parser = argparse.ArgumentParser(description="Run quality-only battle test suite")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("data/qvm/backtest/experiments/quality_battletest"))
    args = parser.parse_args(sys.argv[1:])

    result = run_quality_battle_test_suite(
        start_year=args.start_year,
        end_year=args.end_year,
        top_n=args.top_n,
        output_dir=args.output_dir,
    )

    print(f"One-factor comparison CSV: {result.experiment_suite.comparison_path}")
    print(f"Leave-one-year-out CSV: {result.leave_one_year_out_path}")
    for row in result.experiment_suite.rows:
        print(
            f"{row.experiment} | "
            f"CAGR={row.cagr:.2%} | "
            f"Sharpe={row.sharpe:.2f} | "
            f"MaxDD={row.max_drawdown:.2%} | "
            f"Turnover={row.turnover:.2%} | "
            f"WinRate={row.win_rate_vs_spy:.2%}"
        )


def quality_diagnostics_cli() -> None:
    """Run effective-weight analysis and one-metric quality ablations."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "strategies" / "qvm" / "quality_diagnostics.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Quality diagnostics script not found: {script_path}")

    sys.path.insert(0, str(repo_root))
    runpy.run_path(str(script_path), run_name="__main__")


def selection_diagnostics_cli() -> None:
    """Compute selection diagnostics for a target year and universe regime comparison by year."""
    parser = argparse.ArgumentParser(description="Run QVM selection diagnostics")
    parser.add_argument("--year", type=int, default=date.today().year, help="Formation year to diagnose")
    parser.add_argument("--start-year", type=int, default=2015, help="Start year for universe regime comparison")
    parser.add_argument("--end-year", type=int, default=date.today().year, help="End year for universe regime comparison")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--scoring-mode", type=str, default="quality", choices=["qv", "quality", "valuation"])
    parser.add_argument("--selection-policy", type=str, default="score")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/qvm/backtest/selection_diagnostics"),
        help="Directory for diagnostics CSV outputs",
    )
    args = parser.parse_args(sys.argv[1:])

    if args.start_year > args.end_year:
        raise ValueError("start-year cannot be greater than end-year")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    universe = load_universe()

    # 1) Target-year diagnostics for selected portfolio vs eligible universe.
    companies = score_universe_for_year(args.year, universe)
    for company in companies:
        company.quality = analyse_quality(company)
    eligible = [company for company in companies if quality_eligible(company)]
    selected = select_companies(
        eligible,
        top_n=args.top_n,
        scoring_mode=args.scoring_mode,
        selection_policy=args.selection_policy,
        quality_pool_size=20,
        valuation_guard_min_score=20.0,
    )

    target_row = build_selection_diagnostics_row(
        formation_year=args.year,
        eligible_companies=eligible,
        selected_companies=selected,
    )
    target_path = output_dir / f"selection_diagnostics_{args.year}.csv"
    pd.DataFrame([target_row]).to_csv(target_path, index=False)

    # 2) Universe-only regime comparison by year (selection = universe to isolate market context).
    regime_rows: list[dict[str, object]] = []
    for year in range(args.start_year, args.end_year + 1):
        year_companies = score_universe_for_year(year, universe)
        for company in year_companies:
            company.quality = analyse_quality(company)
        year_eligible = [company for company in year_companies if quality_eligible(company)]
        row = build_selection_diagnostics_row(
            formation_year=year,
            eligible_companies=year_eligible,
            selected_companies=year_eligible,
        )
        regime_rows.append(
            {
                "formation_year": row["formation_year"],
                "universe_n": row["universe_n"],
                "universe_val_median": row["universe_val_median"],
                "universe_expensive_share": row["universe_expensive_share"],
                "universe_cheap_share": row["universe_cheap_share"],
                "universe_quality_median": row["universe_quality_median"],
                "universe_coverage_median": row["universe_coverage_median"],
            }
        )

    regime_df = pd.DataFrame(regime_rows)
    regime_path = output_dir / "universe_valuation_regime_by_year.csv"
    regime_df.to_csv(regime_path, index=False)

    richest = regime_df.sort_values("universe_expensive_share", ascending=False).head(3)
    cheapest = regime_df.sort_values("universe_cheap_share", ascending=False).head(3)

    print(f"Target-year diagnostics CSV: {target_path}")
    print(f"Universe regime CSV: {regime_path}")
    print(
        "Target year summary | "
        f"year={args.year} | "
        f"eligible_n={target_row['universe_n']} | "
        f"selected_n={target_row['selected_n']} | "
        f"universe_val_median={target_row['universe_val_median']:.2f} | "
        f"selected_val_median={target_row['selected_val_median']:.2f} | "
        f"val_median_spread={target_row['val_median_spread']:+.2f}"
    )
    print("Top 3 rich years by universe_expensive_share:")
    for _, row in richest.iterrows():
        print(
            f"  {int(row['formation_year'])} | "
            f"expensive_share={row['universe_expensive_share']:.4f} | "
            f"val_median={row['universe_val_median']:.2f}"
        )
    print("Top 3 cheap years by universe_cheap_share:")
    for _, row in cheapest.iterrows():
        print(
            f"  {int(row['formation_year'])} | "
            f"cheap_share={row['universe_cheap_share']:.4f} | "
            f"val_median={row['universe_val_median']:.2f}"
        )


if __name__ == "__main__":
    company_cli()
