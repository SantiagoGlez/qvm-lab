#!/usr/bin/env python3
"""
Valuation diagnostics: compare Yahoo live PE against the CompaniesMarketCap
historical CSV to surface any staleness or mismatch.

Usage:
    uv run python scripts/strategies/qvm/debug_valuation.py MSFT
"""

import sys
from pathlib import Path

import yfinance as yf

# Resolve project src
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from quantlab.strategies.qvm.providers.companiesmarketcap import CompaniesMarketCapProvider


def pct_diff(a: float | None, b: float | None) -> str:
    if a is None or b is None or b == 0:
        return "-"
    return f"{((a - b) / b) * 100:+.1f}%"


def main(ticker: str) -> None:
    print("=" * 70)
    print(f"Valuation Diagnostics: {ticker}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Yahoo — live snapshot
    # ------------------------------------------------------------------

    stock = yf.Ticker(ticker)
    info = stock.info

    price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or info.get("previousClose")
    )
    trailing_eps = info.get("trailingEps")
    trailing_pe  = info.get("trailingPE")
    forward_pe   = info.get("forwardPE")

    computed_pe: float | None = None
    if price and trailing_eps and float(trailing_eps) > 0:
        computed_pe = float(price) / float(trailing_eps)

    print("\nYahoo")
    print("-" * 70)
    print(f"Price               : {price}")
    print(f"Trailing EPS        : {trailing_eps}")
    print(f"Trailing PE (Yahoo) : {trailing_pe}")
    print(f"Forward PE          : {forward_pe}")
    if computed_pe is not None:
        print(f"Computed PE         : {computed_pe:.2f}  (Price / Trailing EPS)")
    else:
        print("Computed PE         : -  (missing price or EPS)")

    # ------------------------------------------------------------------
    # Historical — CompaniesMarketCap CSV
    # ------------------------------------------------------------------

    provider = CompaniesMarketCapProvider()
    try:
        summary_row = provider._load_summary_row(ticker.upper())
        slug = summary_row["slug"]
        facts = provider._load_valuation_facts(ticker.upper(), slug)
    except Exception as exc:
        print(f"\n[ERROR] Could not load historical data: {exc}")
        return

    if facts is None:
        print("\n[ERROR] No historical PE data found in CSV.")
        return

    csv_current       = facts["current_pe"]
    csv_average       = facts["historical_average_pe"]
    csv_median        = facts["historical_median_pe"]
    csv_percentile    = facts["historical_percentile"]
    pe_values: list   = facts["historical_pe_values"]

    print("\nHistorical (CompaniesMarketCap CSV)")
    print("-" * 70)
    print(f"Current PE (CSV)    : {csv_current:.2f}  ← most recent year in CSV")
    print(f"Average PE          : {csv_average:.2f}")
    print(f"Median PE           : {csv_median:.2f}")
    print(f"Minimum PE          : {min(pe_values):.2f}")
    print(f"Maximum PE          : {max(pe_values):.2f}")
    print(f"Percentile (CSV PE) : {csv_percentile:.1%}")
    print(f"Observations        : {len(pe_values)}")

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    print("\nComparison")
    print("-" * 70)
    print(f"Yahoo Computed vs CSV current  : {pct_diff(computed_pe, csv_current)}")
    print(f"Yahoo Trailing PE vs CSV avg   : {pct_diff(trailing_pe, csv_average)}")

    if computed_pe is not None and pe_values:
        import pandas as pd
        series = pd.Series(pe_values[:-1] + [computed_pe])
        live_percentile = float(series.rank(method="average", pct=True).iloc[-1])
        print(f"Percentile (live Yahoo PE)     : {live_percentile:.1%}")
        print(f"Percentile shift vs CSV        : {(live_percentile - csv_percentile) * 100:+.1f} pp")

    # ------------------------------------------------------------------
    # Full historical series
    # ------------------------------------------------------------------

    print("\nHistorical PE series (used in scoring)")
    print("-" * 70)
    print("  Year  │  PE")
    print("  ──────┼──────")
    # pe_values is sorted ascending; try to pair with years from CSV
    try:
        valuation_path = provider._find_valuation_path(ticker.upper(), slug)
        if valuation_path:
            import pandas as pd_
            df = pd_.read_csv(valuation_path)
            df = df[df["Year"].apply(lambda y: str(y).isdigit())]
            df["Year"] = df["Year"].astype(int)
            df = df.sort_values("Year").tail(len(pe_values))
            for _, row in df.iterrows():
                marker = " ← live" if row["pe_ratio"] == csv_current else ""
                print(f"  {int(row['Year'])}  │  {row['pe_ratio']:.2f}{marker}")
    except Exception:
        for v in pe_values:
            print(f"         │  {v:.2f}")

    print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:")
        print("  uv run python scripts/strategies/qvm/debug_valuation.py MSFT")
        raise SystemExit(1)

    main(sys.argv[1])
