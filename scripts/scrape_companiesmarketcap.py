import re
import unicodedata
from io import StringIO
from pathlib import Path

import pandas as pd
import requests


COMPANY_SLUG_OVERRIDES = {
    "GOOGL": "alphabet-google",
    "RHHBY": "roche",
    "MA": "mastercard",
    "V": "visa",
    "JNJ": "johnson-and-johnson",
    "COST": "costco",
    "AMZN": "amazon",
    "LOW": "lowes-companies",
    "UNH": "united-health",
    "MCD": "mcdonald",
    "RNO": "renault",
}


def normalize_company_slug(name: str) -> str:
    name = str(name).strip()
    name = re.sub(r"\(.*?\)", "", name)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[&+]+", " and ", name)
    name = re.sub(r"['\']", "", name)  # strip apostrophes before general replacement
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def load_companies(csv_path: Path) -> list[tuple[str, str]]:
    df = pd.read_csv(csv_path, dtype=str)
    if "ticker" not in df.columns or "name" not in df.columns:
        raise ValueError(f"CSV file must contain 'ticker' and 'name' columns: {csv_path}")
    companies = []
    for _, row in df.dropna(subset=["ticker", "name"]).iterrows():
        companies.append((row["ticker"].strip(), row["name"].strip()))
    return companies


def resolve_company_slug(ticker: str, name: str) -> str:
    override = COMPANY_SLUG_OVERRIDES.get(ticker.strip().upper())
    if override:
        return override
    normalized = normalize_company_slug(name)
    return normalized or ticker.strip().lower()


class CompaniesMarketCapScraper:
    def __init__(self):
        self.base_url = "https://companiesmarketcap.com/{company}/{metric}/"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }
        self.metrics_map = {
            "revenue": "revenue",
            "net_income": "earnings",
            "pe_ratio": "pe-ratio",
            "cash": "cash-on-hand",
            "total_assets": "total-assets",
            "dividend_yield": "dividend-yield",
        }

    def _clean_financial_value(self, val):
        if pd.isna(val):
            return None
        if not isinstance(val, str):
            return val

        val = val.strip().replace("$", "").replace(",", "")
        if val == "":
            return None

        multiplier = 1.0
        if val.endswith("T"):
            multiplier = 1e12
            val = val[:-1]
        elif val.endswith("B"):
            multiplier = 1e9
            val = val[:-1]
        elif val.endswith("M"):
            multiplier = 1e6
            val = val[:-1]
        elif val.endswith("K"):
            multiplier = 1e3
            val = val[:-1]

        try:
            return float(val) * multiplier
        except ValueError:
            return None

    def _normalize_year(self, year_label: str):
        if pd.isna(year_label):
            return None

        year_label = str(year_label).strip()
        if year_label.upper().startswith("TTM"):
            return "TTM"

        match = re.search(r"(\d{4})", year_label)
        if match:
            return int(match.group(1))

        return year_label

    def get_company_metric(self, company_slug: str, metric_key: str) -> pd.DataFrame | None:
        metric_slug = self.metrics_map.get(metric_key)
        if not metric_slug:
            raise ValueError(f"Métrica '{metric_key}' no soportada.")

        url = self.base_url.format(company=company_slug, metric=metric_slug)
        response = requests.get(url, headers=self.headers, timeout=20)

        if response.status_code != 200:
            print(f"Error {response.status_code} al consultar: {url}")
            return None

        try:
            tables = pd.read_html(StringIO(response.text), flavor="bs4")
        except Exception as exc:
            print(f"Error parsing HTML para {company_slug} / {metric_key}: {exc}")
            return None

        if not tables:
            print(f"No tables found for {company_slug} / {metric_key}")
            return None

        try:
            df = tables[0]
        except Exception:
            print(f"Unable to select table 0 for {company_slug} / {metric_key}")
            return None

        if df.shape[1] < 2:
            print(f"Unexpected table shape for {company_slug} / {metric_key}: {df.shape}")
            return None

        df.columns = ["Year", metric_key] + [f"extra_{i}" for i in range(df.shape[1] - 2)]
        df = df[["Year", metric_key]]
        df[metric_key] = df[metric_key].astype(str).apply(self._clean_financial_value)
        df["Year"] = df["Year"].astype(str).apply(self._normalize_year)
        return df.dropna(subset=[metric_key])


def build_valuation_dataset(scraper: CompaniesMarketCapScraper, company_slug: str, metrics_list: list[str]) -> pd.DataFrame | None:
    main_df = None
    for metric in metrics_list:
        df_metric = scraper.get_company_metric(company_slug, metric)
        if df_metric is None:
            continue

        if main_df is None:
            main_df = df_metric
        else:
            main_df = pd.merge(main_df, df_metric, on="Year", how="outer")

    if main_df is None:
        return None

    return main_df.sort_values(by="Year", ascending=False).reset_index(drop=True)


def main() -> None:
    base_dir = Path.cwd()
    input_csv = base_dir / "data" / "qvm" / "companies.csv"
    output_dir = base_dir / "data" / "qvm" / "companiesmarketcap"
    output_dir.mkdir(parents=True, exist_ok=True)

    companies = load_companies(input_csv)
    scraper = CompaniesMarketCapScraper()
    metrics = ["revenue", "net_income", "pe_ratio", "cash", "total_assets", "dividend_yield"]
    summary_rows = []

    for ticker, name in companies:
        company_slug = resolve_company_slug(ticker, name)
        out_path = output_dir / f"{ticker.lower()}_{company_slug}_valuation.csv"

        # Skip if we already have the file locally
        if out_path.exists():
            try:
                existing_df = pd.read_csv(out_path)
                existing_rows = len(existing_df)
            except Exception:
                existing_rows = None
            print(f"Skipping {ticker} - existing file {out_path.name} ({existing_rows or '?'} rows)")

            # Record skipped status for reporting
            for metric in metrics:
                summary_rows.append(
                    {
                        "ticker": ticker,
                        "name": name,
                        "slug": company_slug,
                        "metric": metric,
                        "status": "skipped",
                        "rows": existing_rows or 0,
                    }
                )
            continue

        print(f"Building dataset for {ticker} / {name} -> slug={company_slug}...")
        df = build_valuation_dataset(scraper, company_slug, metrics)

        for metric in metrics:
            summary_rows.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "slug": company_slug,
                    "metric": metric,
                    "status": "ok" if df is not None and metric in df.columns else "missing",
                    "rows": len(df) if df is not None else 0,
                }
            )

        if df is None or df.empty:
            print(f"  No data assembled for {ticker} / {name}")
            continue

        path = output_dir / f"{ticker.lower()}_{company_slug}_valuation.csv"
        df.to_csv(path, index=False)
        print(f"  Saved {path} ({len(df)} rows, {len(df.columns)} cols)")

    summary_path = output_dir / "companiesmarketcap_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    print(f"Saved summary to {summary_path}")
    print("Done.")


if __name__ == "__main__":
    main()
