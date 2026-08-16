import argparse
import runpy
import sys
from pathlib import Path

from quantlab.strategies.qvm.backtest.annual import (
    AnnualBacktestConfig,
    run_annual_backtest,
    run_experiment_suite,
    run_quality_battle_test_suite,
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
    print(
        "Summary | "
        f"years={result.summary.years} | "
        f"portfolio_cagr={result.summary.portfolio_cagr:.2%} | "
        f"benchmark_cagr={result.summary.benchmark_cagr:.2%} | "
        f"win_rate={result.summary.win_rate:.2%}"
    )


def experiments_cli() -> None:
    """Run a set of annual backtest experiments and write a comparison table."""
    parser = argparse.ArgumentParser(description="Run QVM backtest experiment suite")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("data/qvm/backtest/experiments"))
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
    ]

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


if __name__ == "__main__":
    company_cli()
