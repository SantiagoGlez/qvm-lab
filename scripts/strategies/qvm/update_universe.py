from pathlib import Path
import traceback

import pandas as pd

from quantlab.strategies.qvm.analysis.overall import overall_score
from quantlab.strategies.qvm.service import analyse_company


DATA_DIR = Path("data/qvm")

INPUT_FILE  = DATA_DIR / "companies.csv"
OUTPUT_FILE = DATA_DIR / "results.csv"

_PORTFOLIO_ORDER = ["Sell", "Reduce", "Review", "Accumulate", "Hold"]
_WATCHLIST_ORDER = ["Buy", "Watch", "Avoid"]


def _print_table(df, title):
    print(f"=== {title} ===")
    print()
    if df.empty:
        print("  (none)")
        print()
        return
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1200)
    pd.set_option("display.max_colwidth", None)
    print(df.to_string(index=False))
    print()


def main():

    companies = pd.read_csv(INPUT_FILE)
    results = []

    for _, row in companies.iterrows():
        ticker = row["ticker"]
        print(f"Processing {ticker}...")
        try:
            company = analyse_company(ticker)
            results.append({
                "ticker":            company.ticker,
                "name":              company.name,
                "sector":            company.sector,
                "industry":          company.industry,
                "updated":           company.last_updated.isoformat(),
                "forward_pe":        company.metrics.forward_pe,
                "trailing_pe":       company.metrics.trailing_pe,
                "roe":               company.metrics.roe,
                "gross_margin":      company.metrics.gross_margin,
                "operating_margin":  company.metrics.operating_margin,
                "valuation":         company.valuation.score,
                "quality":           company.quality.score,
                "overall":           overall_score(company),
                "market_assessment": company.momentum.recommendation,
                "action":            company.portfolio.action,
                "owned":             company.portfolio.owned,
            })
        except Exception as ex:
            print(f"X {ticker}: {ex}")
            traceback.print_exc()

    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_FILE, index=False)
    print()
    print(f"Saved {len(df)} companies to {OUTPUT_FILE}")
    print()

    display_cols = ["ticker", "name", "valuation", "quality", "market_assessment", "action"]

    # Truncate name for display so the table fits on one line
    for frame_df in [df]:
        frame_df["name"] = frame_df["name"].str.slice(0, 28)

    portfolio_df = df[df["owned"]].copy()
    if not portfolio_df.empty:
        portfolio_df["_sort"] = portfolio_df["action"].map(
            {a: i for i, a in enumerate(_PORTFOLIO_ORDER)}
        ).fillna(len(_PORTFOLIO_ORDER))
        portfolio_df = portfolio_df.sort_values("_sort")[display_cols]
    else:
        portfolio_df = portfolio_df[display_cols]
    _print_table(portfolio_df, "Portfolio")

    watchlist_df = df[~df["owned"]].copy()
    if not watchlist_df.empty:
        watchlist_df["_sort"] = watchlist_df["action"].map(
            {a: i for i, a in enumerate(_WATCHLIST_ORDER)}
        ).fillna(len(_WATCHLIST_ORDER))
        watchlist_df = watchlist_df.sort_values("_sort")[display_cols]
    else:
        watchlist_df = watchlist_df[display_cols]
    _print_table(watchlist_df, "Watchlist")


if __name__ == "__main__":
    main()
