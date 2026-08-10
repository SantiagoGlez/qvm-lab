import re
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

try:
    from scripts.scrape_companiesmarketcap import load_companies, resolve_company_slug
except ImportError:
    from scrape_companiesmarketcap import load_companies, resolve_company_slug


REQUIRED_COLUMNS = [
    "year",
    "revenue",
    "eps",
    "net_income",
    "operating_margin",
    "cash",
    "total_debt",
    "total_assets",
    "net_assets",
    "pe_ratio",
]

OPTIONAL_COLUMNS = [
    "total_liabilities",
    "shares_outstanding",
    "dividend_yield",
    "price_to_sales",
    "price_to_book",
]

# Canonical output column -> CompaniesMarketCap metric slug candidates.
METRIC_SLUG_CANDIDATES = {
    "revenue": ["revenue"],
    "eps": ["eps"],
    "net_income": ["earnings"],
    "operating_margin": ["operating-margin"],
    "cash": ["cash-on-hand"],
    "total_debt": ["total-debt"],
    "total_assets": ["total-assets"],
    "net_assets": ["net-assets"],
    "pe_ratio": ["pe-ratio"],
    "total_liabilities": ["total-liabilities"],
    "shares_outstanding": ["shares-outstanding"],
    "dividend_yield": ["dividend-yield"],
    "price_to_sales": ["ps-ratio"],
    "price_to_book": ["pb-ratio"],
}


class CompaniesMarketCapFinancialsScraper:
    def __init__(self) -> None:
        self.base_url = "https://companiesmarketcap.com/{company}/{metric}/"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }

    def _clean_financial_value(self, value: object) -> float | None:
        if pd.isna(value):
            return None

        text = str(value).strip()
        if text == "":
            return None

        negative = False
        if text.startswith("(") and text.endswith(")"):
            negative = True
            text = text[1:-1]

        text = text.replace("$", "").replace(",", "").replace("%", "")
        text = text.replace("USD", "").strip()

        multiplier = 1.0
        if text.endswith("T"):
            multiplier = 1e12
            text = text[:-1]
        elif text.endswith("B"):
            multiplier = 1e9
            text = text[:-1]
        elif text.endswith("M"):
            multiplier = 1e6
            text = text[:-1]
        elif text.endswith("K"):
            multiplier = 1e3
            text = text[:-1]

        try:
            number = float(text) * multiplier
            return -number if negative else number
        except ValueError:
            return None

    def _normalize_year(self, year_label: object) -> int | None:
        if pd.isna(year_label):
            return None

        year_text = str(year_label).strip()
        if year_text.upper().startswith("TTM"):
            return None

        match = re.search(r"(\d{4})", year_text)
        if not match:
            return None

        return int(match.group(1))

    def _fetch_html(self, company_slug: str, metric_slug: str) -> str | None:
        url = self.base_url.format(company=company_slug, metric=metric_slug)
        try:
            response = requests.get(url, headers=self.headers, timeout=20)
        except requests.RequestException as exc:
            print(f"  Request failed for {company_slug}/{metric_slug}: {exc}")
            return None

        if response.status_code != 200:
            return None

        return response.text

    def discover_metric_slugs(self, company_slug: str) -> set[str]:
        seed_metrics = ["revenue", "earnings", "pe-ratio"]
        for seed_metric in seed_metrics:
            html = self._fetch_html(company_slug, seed_metric)
            if not html:
                continue

            pattern = rf'href="/(?:[a-z]{{3}}/)?{re.escape(company_slug)}/([a-z0-9-]+)/"'
            slugs = set(re.findall(pattern, html))
            if slugs:
                return slugs

        return set()

    def get_annual_metric(self, company_slug: str, metric_slug: str, output_column: str) -> pd.DataFrame | None:
        html = self._fetch_html(company_slug, metric_slug)
        if not html:
            return None

        try:
            tables = pd.read_html(StringIO(html), flavor="bs4")
        except Exception:
            return None

        if not tables:
            return None

        table = tables[0]
        if table.shape[1] < 2:
            return None

        # The first two columns are always year + metric value; later columns are deltas.
        metric_df = table.iloc[:, :2].copy()
        metric_df.columns = ["year", output_column]
        metric_df["year"] = metric_df["year"].apply(self._normalize_year)
        metric_df[output_column] = metric_df[output_column].apply(self._clean_financial_value)
        metric_df = metric_df.dropna(subset=["year"])

        if metric_df.empty:
            return None

        metric_df = metric_df.groupby("year", as_index=False).first()
        return metric_df


def _merge_metric(base_df: pd.DataFrame | None, metric_df: pd.DataFrame) -> pd.DataFrame:
    if base_df is None:
        return metric_df.copy()
    return pd.merge(base_df, metric_df, on="year", how="outer")


def build_financials_dataset(
    scraper: CompaniesMarketCapFinancialsScraper,
    company_slug: str,
    max_years: int = 15,
) -> tuple[pd.DataFrame | None, dict[str, str | None]]:
    discovered_slugs = scraper.discover_metric_slugs(company_slug)
    metric_sources: dict[str, str | None] = {column: None for column in METRIC_SLUG_CANDIDATES}

    dataset = None

    for output_column, slug_candidates in METRIC_SLUG_CANDIDATES.items():
        chosen_slug = None
        if discovered_slugs:
            for slug in slug_candidates:
                if slug in discovered_slugs:
                    chosen_slug = slug
                    break
        else:
            chosen_slug = slug_candidates[0]

        if not chosen_slug:
            continue

        metric_df = scraper.get_annual_metric(company_slug, chosen_slug, output_column)
        if metric_df is None:
            continue

        metric_sources[output_column] = chosen_slug
        dataset = _merge_metric(dataset, metric_df)

    if dataset is None or dataset.empty:
        return None, metric_sources

    dataset["year"] = pd.to_numeric(dataset["year"], errors="coerce")
    dataset = dataset.dropna(subset=["year"])
    dataset["year"] = dataset["year"].astype(int)
    dataset = dataset.sort_values("year", ascending=False).drop_duplicates(subset=["year"]).head(max_years)
    dataset = dataset.sort_values("year", ascending=False).reset_index(drop=True)

    # Always expose required schema. Missing values stay blank in CSV.
    for column in REQUIRED_COLUMNS:
        if column not in dataset.columns:
            dataset[column] = pd.NA

    optional_present = [column for column in OPTIONAL_COLUMNS if metric_sources[column] is not None]
    ordered_columns = REQUIRED_COLUMNS + optional_present
    dataset = dataset[ordered_columns]

    return dataset, metric_sources


def main() -> None:
    base_dir = Path.cwd()
    input_csv = base_dir / "data" / "qvm" / "companies.csv"
    output_dir = base_dir / "data" / "qvm" / "companiesmarketcap"
    output_dir.mkdir(parents=True, exist_ok=True)

    companies = load_companies(input_csv)
    scraper = CompaniesMarketCapFinancialsScraper()

    summary_rows = []

    for ticker, name in companies:
        company_slug = resolve_company_slug(ticker, name)
        out_path = output_dir / f"{ticker.lower()}_{company_slug}_financials.csv"

        print(f"Building financial history for {ticker} / {name} -> slug={company_slug}...")
        dataset, metric_sources = build_financials_dataset(scraper, company_slug, max_years=15)

        downloaded_metrics = sorted([metric for metric, source in metric_sources.items() if source])
        missing_metrics = sorted([metric for metric, source in metric_sources.items() if not source])
        print(f"  Downloaded metrics ({len(downloaded_metrics)}): {', '.join(downloaded_metrics) if downloaded_metrics else '-'}")
        print(f"  Missing metrics ({len(missing_metrics)}): {', '.join(missing_metrics) if missing_metrics else '-'}")

        for metric, source in metric_sources.items():
            summary_rows.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "slug": company_slug,
                    "metric": metric,
                    "metric_slug": source or "",
                    "status": "ok" if source else "missing",
                    "rows": len(dataset) if dataset is not None else 0,
                }
            )

        if dataset is None or dataset.empty:
            print(f"  No annual financial dataset assembled for {ticker} / {name}")
            continue

        dataset.to_csv(out_path, index=False)
        print(f"  Saved {out_path.name} ({len(dataset)} rows, {len(dataset.columns)} cols)")

    summary_path = output_dir / "companiesmarketcap_financials_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    print(f"Saved financials summary to {summary_path}")
    print("Done.")


if __name__ == "__main__":
    main()
