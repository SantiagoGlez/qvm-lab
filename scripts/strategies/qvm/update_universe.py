from pathlib import Path
import traceback

import pandas as pd

from quantlab.strategies.qvm.analysis.overall import report_overall_score
from quantlab.strategies.qvm.service import analyse_company


DATA_DIR = Path("data/qvm")

INPUT_FILE  = DATA_DIR / "companies.csv"
OUTPUT_FILE = DATA_DIR / "results.csv"

_MARKET_ASSESSMENT_ORDER = ["Attractive", "Near-highs", "Improving", "Recovering", "Weak"]


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


def _sort_for_ranking(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    sort_map = {a: i for i, a in enumerate(_MARKET_ASSESSMENT_ORDER)}
    ranked = df.copy()
    ranked["_market_sort"] = ranked["market_assessment"].map(sort_map).fillna(len(_MARKET_ASSESSMENT_ORDER))
    ranked = ranked.sort_values(
        by=["quality", "historical_valuation", "_market_sort", "ticker"],
        ascending=[False, False, True, True],
    )
    return ranked.drop(columns=["_market_sort"])


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
                "quality":           company.quality.score,
                "historical_valuation": company.valuation.score,
                "intrinsic_valuation":  company.reverse_dcf.assessment,
                "overall":           report_overall_score(company),
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

    display_cols = [
        "ticker",
        "name",
        "quality",
        "historical_valuation",
        "intrinsic_valuation",
        "market_assessment",
        "action",
    ]

    # Truncate name for display so the table fits on one line
    for frame_df in [df]:
        frame_df["name"] = frame_df["name"].str.slice(0, 28)

    portfolio_df = _sort_for_ranking(df[df["owned"]].copy())
    portfolio_df = portfolio_df[display_cols] if not portfolio_df.empty else portfolio_df.reindex(columns=display_cols)
    _print_table(portfolio_df, "Portfolio")

    watchlist_df = _sort_for_ranking(df[~df["owned"]].copy())
    watchlist_df = watchlist_df[display_cols] if not watchlist_df.empty else watchlist_df.reindex(columns=display_cols)
    _print_table(watchlist_df, "Watchlist")


if __name__ == "__main__":
    main()
