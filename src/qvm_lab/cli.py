import argparse
import io
import runpy
import sys
from contextlib import redirect_stdout
from datetime import date, timedelta
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
from quantlab.strategies.qvm.backtest.contribution import (
    ContributionBacktestConfig,
    run_contribution_experiment_suite,
)
from quantlab.strategies.qvm.reports.console import print_report
from quantlab.strategies.qvm.reports.google_finance_chat import run_google_finance_audit
from quantlab.strategies.qvm.service import analyse_company
from quantlab.strategies.qvm.analysis.universal_return import (
    build_universal_inputs,
    calculate_universal_return,
    format_universal_return_report,
)
from quantlab.strategies.qvm.analysis.correlation import build_correlation_analysis, write_correlation_report


def company_cli() -> None:
    """Run QVM analysis for a single ticker and print the full report."""
    parser = argparse.ArgumentParser(description="Run QVM analysis for one ticker")
    parser.add_argument("ticker", help="Ticker symbol to analyze")
    parser.add_argument(
        "--google-finance-audit",
        action="store_true",
        help="Append Google Finance beta chat QA response to the end of the report.",
    )
    parser.add_argument(
        "--google-finance-audit-mode",
        choices=["quick", "full"],
        default="quick",
        help="Prompt mode for Google Finance chat QA.",
    )
    parser.add_argument(
        "--google-finance-timeout-seconds",
        type=int,
        default=120,
        help="Timeout for Google Finance chat response capture.",
    )
    parser.add_argument(
        "--google-finance-show-browser",
        action="store_true",
        help="Run Google Finance chat automation in visible browser mode.",
    )
    args = parser.parse_args(sys.argv[1:])

    company = analyse_company(args.ticker)
    report_buffer = io.StringIO()
    with redirect_stdout(report_buffer):
        print_report(company)

    report_text = report_buffer.getvalue()
    print(report_text, end="")

    if args.google_finance_audit:
        print("Google Finance QA")
        print("-" * 30)
        print()
        audit_result = run_google_finance_audit(
            report_text,
            mode=args.google_finance_audit_mode,
            timeout_seconds=args.google_finance_timeout_seconds,
            headless=not args.google_finance_show_browser,
        )
        if audit_result.success:
            print(audit_result.response)
        else:
            print("Google Finance audit was requested but could not be completed automatically.")
            print(f"Error: {audit_result.error}")
            print()
            print("No prompt/report dump was appended.")
            if "Playwright is not installed" in (audit_result.error or ""):
                print("To run automatic capture, install Playwright:")
                print("  uv add playwright")
                print("  uv run python -m playwright install chromium")
            else:
                print("Next checks:")
                print("  1) Try visible mode: --google-finance-show-browser")
                print("  2) Complete any consent/login challenge in the opened browser")
                print("  3) Re-run with a larger timeout (e.g. --google-finance-timeout-seconds 120)")
            print("Prompt templates are available in docs/specifications.")


def universal_return_cli() -> None:
    """Run standalone Universal Shareholder Return diagnostics."""
    parser = argparse.ArgumentParser(
        description="Run standalone Universal Shareholder Return model"
    )
    parser.add_argument("ticker", nargs="?", help="Ticker symbol to analyze")
    parser.add_argument("--horizon-years", type=int, default=5, help="Projection horizon in years")
    parser.add_argument(
        "--universe-file",
        type=str,
        default="data/qvm/companies.csv",
        help="CSV file with a 'ticker' column for batch ranking",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Rows to print for universe ranking mode",
    )
    parser.add_argument(
        "--min-expected-return",
        type=float,
        default=None,
        help="Optional minimum expected annual return percent filter (e.g. 12)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="data/qvm/universal_return_results.csv",
        help="Write the full universe results to this CSV file in universe mode",
    )
    args = parser.parse_args(sys.argv[1:])

    if args.horizon_years <= 0:
        raise ValueError("--horizon-years must be > 0")

    if args.ticker:
        company = analyse_company(args.ticker)
        inputs = build_universal_inputs(company)
        result = calculate_universal_return(inputs, horizon_years=args.horizon_years)
        print(format_universal_return_report(inputs, result))
        return

    universe_path = Path(args.universe_file)
    if not universe_path.exists():
        raise FileNotFoundError(f"Universe file not found: {universe_path}")

    frame = pd.read_csv(universe_path)
    if "ticker" not in frame.columns:
        raise ValueError(f"Universe file must contain a 'ticker' column: {universe_path}")

    rows: list[dict[str, object]] = []
    for ticker in frame["ticker"].dropna().astype(str).tolist():
        try:
            company = analyse_company(ticker)
            inputs = build_universal_inputs(company)
            result = calculate_universal_return(inputs, horizon_years=args.horizon_years)
            rows.append(
                {
                    "ticker": ticker,
                    "expected_annual_return_pct": (
                        result.expected_annual_return * 100.0
                        if result.expected_annual_return is not None
                        else None
                    ),
                    "line_1_capital_yield_pct": (
                        result.line_1_capital_yield * 100.0
                        if result.line_1_capital_yield is not None
                        else None
                    ),
                    "line_2_growth_pct": (
                        result.line_2_fundamental_growth * 100.0
                        if result.line_2_fundamental_growth is not None
                        else None
                    ),
                    "line_3_valuation_delta_pct": (
                        result.line_3_valuation_delta * 100.0
                        if result.line_3_valuation_delta is not None
                        else None
                    ),
                    "confidence_label": result.confidence_label,
                    "missing_inputs": ", ".join(result.missing_inputs),
                    "warnings_count": len(result.warnings),
                    "assumptions_count": len(result.assumptions),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "ticker": ticker,
                    "expected_annual_return_pct": None,
                    "line_1_capital_yield_pct": None,
                    "line_2_growth_pct": None,
                    "line_3_valuation_delta_pct": None,
                    "confidence_label": "Low",
                    "missing_inputs": "analysis failed",
                    "warnings_count": None,
                    "assumptions_count": None,
                    "error": str(exc),
                }
            )

    full_out = pd.DataFrame(rows)
    if args.min_expected_return is not None:
        display_out = full_out[
            full_out["expected_annual_return_pct"].notna()
            & (full_out["expected_annual_return_pct"] >= args.min_expected_return)
        ]
    else:
        display_out = full_out

    full_out = full_out.sort_values(by=["expected_annual_return_pct", "ticker"], ascending=[False, True])
    display_out = display_out.sort_values(by=["expected_annual_return_pct", "ticker"], ascending=[False, True])
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    full_out.to_csv(output_path, index=False)
    print("Universal Shareholder Return Ranking (Informative)")
    print(f"Saved full universe results to {output_path}")
    print()
    if display_out.empty:
        print("No rows to display.")
        return
    print(display_out.head(max(args.top, 1)).to_string(index=False))


def correlation_cli() -> None:
    """Measure correlation for a portfolio plus optional external reference assets."""
    parser = argparse.ArgumentParser(description="Run portfolio correlation analysis")
    parser.add_argument(
        "--portfolio-file",
        type=Path,
        default=Path("data/qvm/portfolio.csv"),
        help="CSV file with the main portfolio tickers",
    )
    parser.add_argument(
        "--reference-file",
        type=Path,
        default=None,
        help="Optional CSV file with extra reference assets such as gold or bond proxies",
    )
    parser.add_argument(
        "--lookback-years",
        type=int,
        default=5,
        help="How many years of adjusted-close history to use",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/qvm/backtest/correlation"),
        help="Directory for correlation CSV outputs",
    )
    args = parser.parse_args(sys.argv[1:])

    if args.lookback_years <= 0:
        raise ValueError("--lookback-years must be > 0")

    end_date = date.today()
    start_date = end_date - timedelta(days=int(args.lookback_years * 365.25))
    result = build_correlation_analysis(
        portfolio_path=args.portfolio_file,
        reference_path=args.reference_file,
        start=start_date,
        end=end_date,
    )
    matrix_path, summary_path, returns_path = write_correlation_report(result, args.output_dir)

    print(f"Correlation matrix CSV: {matrix_path}")
    print(f"Correlation summary CSV: {summary_path}")
    print(f"Portfolio returns CSV: {returns_path}")
    if result.missing_assets:
        print("Missing price history for:")
        for asset_name in result.missing_assets:
            print(f"  - {asset_name}")
    print()
    print(result.summary_table.to_string(index=False))


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
            selection_policy="quality_intrinsic_guard",
            intrinsic_guard_allowed_assessments=(
                "Very Conservative Expectations",
                "Conservative Expectations",
                "Reasonable Expectations",
            ),
            experiment_name="Quality + Intrinsic Guard (Reasonable+)",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_intrinsic_tilt",
            intrinsic_tilt_weight=0.10,
            intrinsic_tilt_unavailable_score=50.0,
            experiment_name="Quality + Intrinsic Tilt (90/10)",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_intrinsic_tilt",
            intrinsic_tilt_weight=0.15,
            intrinsic_tilt_unavailable_score=50.0,
            experiment_name="Quality + Intrinsic Tilt (85/15)",
        ),
        AnnualBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            formation_month=4,
            formation_day=1,
            scoring_mode="quality",
            selection_policy="quality_intrinsic_guard_tilt",
            intrinsic_guard_allowed_assessments=(
                "Very Conservative Expectations",
                "Conservative Expectations",
                "Reasonable Expectations",
                "Optimistic Expectations",
            ),
            intrinsic_tilt_weight=0.10,
            intrinsic_tilt_unavailable_score=50.0,
            experiment_name="Quality + Intrinsic Hybrid (No Very Optimistic, 90/10)",
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


def contribution_experiments_cli() -> None:
    """Run periodic-contribution experiments including tax-aware limited replacement variants."""
    parser = argparse.ArgumentParser(description="Run QVM contribution-aware experiment suite")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--contribution-months", type=int, default=2)
    parser.add_argument("--initial-contribution", type=float, default=1.0)
    parser.add_argument("--contribution-amount", type=float, default=1.0)
    parser.add_argument("--output-dir", type=Path, default=Path("data/qvm/backtest/contribution_portfolio"))
    args = parser.parse_args(sys.argv[1:])

    configs = [
        ContributionBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            rebalance_month=4,
            rebalance_day=1,
            contribution_months=args.contribution_months,
            initial_contribution=args.initial_contribution,
            contribution_amount=args.contribution_amount,
            scoring_mode="quality",
            selection_policy="score",
            rebalance_policy="full_refresh",
            allocation_policy="reset_equal_weight",
            experiment_name="Quality Only + Contributions",
        ),
        ContributionBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            rebalance_month=4,
            rebalance_day=1,
            contribution_months=args.contribution_months,
            initial_contribution=args.initial_contribution,
            contribution_amount=args.contribution_amount,
            scoring_mode="quality",
            selection_policy="score",
            rebalance_policy="limited_replacements",
            max_replacements_per_rebalance=1,
            allocation_policy="reset_equal_weight",
            experiment_name="Quality Only + Contributions + Max 1 Replacement",
        ),
        ContributionBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            rebalance_month=4,
            rebalance_day=1,
            contribution_months=args.contribution_months,
            initial_contribution=args.initial_contribution,
            contribution_amount=args.contribution_amount,
            scoring_mode="quality",
            selection_policy="score",
            rebalance_policy="limited_replacements",
            max_replacements_per_rebalance=1,
            allocation_policy="buy_biased_no_trim",
            experiment_name="Quality Only + Contributions + Max 1 Replacement + No Trims",
        ),
        ContributionBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            rebalance_month=4,
            rebalance_day=1,
            contribution_months=args.contribution_months,
            initial_contribution=args.initial_contribution,
            contribution_amount=args.contribution_amount,
            scoring_mode="quality",
            selection_policy="score",
            rebalance_policy="limited_replacements",
            max_replacements_per_rebalance=1,
            allocation_policy="buy_biased_soft_cap",
            soft_trim_weight_cap=0.15,
            experiment_name="Quality Only + Contributions + Max 1 Replacement + Soft Cap 15%",
        ),
        ContributionBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            rebalance_month=4,
            rebalance_day=1,
            contribution_months=args.contribution_months,
            initial_contribution=args.initial_contribution,
            contribution_amount=args.contribution_amount,
            scoring_mode="quality",
            selection_policy="score",
            rebalance_policy="limited_replacements_adaptive",
            max_replacements_per_rebalance=1,
            adaptive_max_replacements_per_rebalance=3,
            adaptive_quality_drop_threshold=15.0,
            allocation_policy="buy_biased_soft_cap",
            soft_trim_weight_cap=0.15,
            experiment_name="Quality Only + Contributions + Max 1->3 Adaptive + Soft Cap 15%",
        ),
        ContributionBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            rebalance_month=4,
            rebalance_day=1,
            contribution_months=args.contribution_months,
            initial_contribution=args.initial_contribution,
            contribution_amount=args.contribution_amount,
            scoring_mode="quality",
            selection_policy="score",
            rebalance_policy="limited_replacements",
            max_replacements_per_rebalance=2,
            allocation_policy="reset_equal_weight",
            experiment_name="Quality Only + Contributions + Max 2 Replacements",
        ),
        ContributionBacktestConfig(
            start_year=args.start_year,
            end_year=args.end_year,
            top_n=args.top_n,
            rebalance_month=4,
            rebalance_day=1,
            contribution_months=args.contribution_months,
            initial_contribution=args.initial_contribution,
            contribution_amount=args.contribution_amount,
            scoring_mode="quality",
            selection_policy="score",
            rebalance_policy="limited_replacements",
            max_replacements_per_rebalance=1,
            allocation_policy="buy_biased_seasonal_dip_deploy",
            soft_trim_weight_cap=0.15,
            dip_deploy_trigger_month=9,
            dip_deploy_drawdown_threshold=0.08,
            dip_deploy_base_invest_fraction=0.35,
            experiment_name="Quality Only + Contributions + Sep Dip Deploy",
        ),
    ]

    suite = run_contribution_experiment_suite(configs=configs, output_dir=args.output_dir)
    print(f"Comparison CSV: {suite.comparison_path}")
    for row in suite.rows:
        print(
            f"{row.experiment} | "
            f"Policy={row.rebalance_policy} | "
            f"MaxRepl={row.max_replacements_per_rebalance} | "
            f"AdaptiveMaxRepl={row.adaptive_max_replacements_per_rebalance} | "
            f"DropThr={row.adaptive_quality_drop_threshold:.1f} | "
            f"Allocation={row.allocation_policy} | "
            f"Cap={row.soft_trim_weight_cap:.0%} | "
            f"TWR_CAGR={row.twr_cagr:.2%} | "
            f"MWRR={row.mwrr:.2%} | "
            f"Turnover={suite.run_results[row.experiment].summary.turnover:.2%} | "
            f"Benchmark_TWR_CAGR={row.benchmark_twr_cagr:.2%} | "
            f"Benchmark_MWRR={row.benchmark_mwrr:.2%} | "
            f"WinRate={row.win_rate:.2%}"
        )


def quality_diagnostics_cli() -> None:
    """Run effective-weight analysis and one-metric quality ablations."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "strategies" / "qvm" / "quality_diagnostics.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Quality diagnostics script not found: {script_path}")

    sys.path.insert(0, str(repo_root))
    runpy.run_path(str(script_path), run_name="__main__")


def top_winners_evolution_cli() -> None:
    """Export yearly factor evolution for top price winners in the backtest window."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "strategies" / "qvm" / "analyze_top_price_winners.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Top winners script not found: {script_path}")

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
