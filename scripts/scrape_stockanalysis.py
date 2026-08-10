import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


def load_tickers(csv_path: Path) -> list[str]:
    df = pd.read_csv(csv_path)
    if "ticker" not in df.columns:
        raise ValueError(f"CSV file must contain a 'ticker' column: {csv_path}")
    return df["ticker"].astype(str).str.strip().dropna().unique().tolist()


def normalize_metric_label(text: str) -> str:
    text = text.strip()
    text = " ".join(text.split())

    # Collapse duplicate metric labels like "Revenue Revenue Growth"
    text = re.sub(r"^(?P<base>.+?)\s+(?P=base)\s+Growth$", r"\g<base>", text, flags=re.I)
    text = re.sub(r"\s+EPS\s+Growth$", "", text, flags=re.I)
    return text


def parse_stockanalysis_table(table: BeautifulSoup, symbol: str) -> pd.DataFrame | None:
    headers = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
        if header_row:
            headers = [cell.get_text(" ", strip=True) for cell in header_row.find_all(["th", "td"])]

    if not headers:
        first_row = table.find("tr")
        if first_row:
            headers = [cell.get_text(" ", strip=True) for cell in first_row.find_all(["th", "td"])]

    rows = []
    if table.find("tbody"):
        row_elements = table.find("tbody").find_all("tr")
    else:
        row_elements = table.find_all("tr")[1:]

    for row_el in row_elements:
        row_cells = row_el.find_all(["th", "td"])
        if not row_cells:
            continue
        row = [normalize_metric_label(cell.get_text(" ", strip=True)) for cell in row_cells]
        if headers and len(row) >= len(headers):
            rows.append(row[: len(headers)])
        elif not headers:
            rows.append(row)

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=headers if headers else None)
    if df.columns.size > 0:
        df.rename(columns={df.columns[0]: "Metric"}, inplace=True)
    df.insert(0, "Ticker", symbol.upper())
    return df


def scrape_stockanalysis_financials(symbol: str) -> pd.DataFrame | None:
    url = f"https://stockanalysis.com/stocks/{symbol.lower()}/financials/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(
                f"❌ [{symbol}] Failed request with HTTP Status Code: {response.status_code}"
            )
            return None

        soup = BeautifulSoup(response.content, "html.parser")
        table = soup.find("table", {"data-test": "financials-table"})
        if not table:
            table = soup.find("table")

        if not table:
            print(f"❌ [{symbol}] Financial table not found.")
            return None

        df = parse_stockanalysis_table(table, symbol)
        if df is None or df.empty:
            print(f"❌ [{symbol}] Failed to parse financial table.")
            return None

        years = len(df.columns) - 2
        print(f"✓ [{symbol}] Retrieved {years} years of financial data.")
        return df

    except Exception as exc:
        print(f"❌ [{symbol}] Error scraping data: {exc}")
        return None


def extract_metric_history(
    financials_dict: dict[str, pd.DataFrame | None],
    metric_name: str = "EPS (Diluted)",
) -> pd.DataFrame:
    records = []
    fallback_patterns = [r"earnings per share", r"eps", r"diluted eps"]

    for ticker, df in financials_dict.items():
        if df is None or df.empty:
            continue

        row = df[df["Metric"].str.strip().str.lower() == metric_name.lower()]
        if row.empty:
            try:
                row = df[df["Metric"].str.contains(metric_name, case=False, na=False, regex=False)]
            except Exception:
                row = pd.DataFrame()

        if row.empty:
            row = df[df["Metric"].str.contains(r"earnings per share|eps", case=False, na=False, regex=True)]

        if row.empty:
            row = df[df["Metric"].str.lower().isin(fallback_patterns)]

        if not row.empty:
            record = row.iloc[0].to_dict()
            records.append(record)

    if not records:
        return pd.DataFrame()

    metric_df = pd.DataFrame(records)
    metric_df.drop(columns=["Metric"], errors="ignore", inplace=True)

    year_cols = [c for c in metric_df.columns if c != "Ticker"]
    metric_df = metric_df[["Ticker"] + year_cols]
    return metric_df


def main() -> None:
    base_dir = Path.cwd()
    csv_path = base_dir / "data" / "qvm" / "companies.csv"
    output_dir = base_dir / "data" / "qvm" / "stockanalysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading tickers from {csv_path}...")
    target_tickers = load_tickers(csv_path)
    print(f"Target tickers loaded: {target_tickers}\n")

    financials = {}
    for ticker in target_tickers:
        print(f"Scraping {ticker}...")
        financials[ticker] = scrape_stockanalysis_financials(ticker)
        time.sleep(1.5)

    eps_history = extract_metric_history(financials, metric_name="EPS (Diluted)")
    if not eps_history.empty:
        eps_history.to_csv(output_dir / "historical_eps_10yr.csv", index=False)
        print(f"Saved EPS history to {output_dir / 'historical_eps_10yr.csv'}")
    else:
        print("No EPS history rows extracted.")

    for ticker, df in financials.items():
        if df is not None and not df.empty:
            df.to_csv(output_dir / f"{ticker}_income_statement.csv", index=False)

    print(f"Saved scraped StockAnalysis files to {output_dir}")


if __name__ == "__main__":
    main()
