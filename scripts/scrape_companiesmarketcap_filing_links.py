import argparse
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

try:
    from scripts.scrape_companiesmarketcap import load_companies, resolve_company_slug
except ImportError:
    from scrape_companiesmarketcap import load_companies, resolve_company_slug


PAGE_CONFIG = {
    "annual-reports-10k": "10k",
    "annual-reports": "annual-report",
}


def _extract_report_year(text: str) -> int | None:
    years = [
        int(year)
        for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?:\d{4})?(?!\d)", text)
        if 1900 <= int(year) <= 2100
    ]
    if not years:
        sec_two_digit = re.search(r"-(\d{2})-", text)
        if sec_two_digit:
            yy = int(sec_two_digit.group(1))
            return 2000 + yy if yy <= 30 else 1900 + yy
        return None
    return max(years)


def _normalize_pdf_url(href: str, page_url: str) -> str:
    absolute = urljoin(page_url, href)
    parsed = urlparse(absolute)
    return parsed._replace(query="", fragment="").geturl()


def extract_filing_links_from_html(html: str, page_url: str, page_metric: str) -> list[dict[str, Any]]:
    hrefs = re.findall(r'href="([^\"]+)"', html)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for href in hrefs:
        normalized_url = _normalize_pdf_url(href, page_url)
        path_lower = urlparse(normalized_url).path.lower()

        if not path_lower.endswith(".pdf"):
            continue
        if f"/{page_metric}/" not in path_lower:
            continue
        if normalized_url in seen:
            continue

        seen.add(normalized_url)
        file_name = Path(urlparse(normalized_url).path).name
        rows.append(
            {
                "page_metric": page_metric,
                "report_type": PAGE_CONFIG.get(page_metric, page_metric),
                "page_url": page_url,
                "file_url": normalized_url,
                "file_name": file_name,
                "report_year": _extract_report_year(file_name),
                "source_href": href,
            }
        )

    return rows


class CompaniesMarketCapFilingLinksScraper:
    def __init__(self) -> None:
        self.base_url = "https://companiesmarketcap.com/{company}/{metric}/"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }

    def _fetch_html(self, company_slug: str, metric_slug: str) -> str | None:
        url = self.base_url.format(company=company_slug, metric=metric_slug)
        try:
            response = requests.get(url, headers=self.headers, timeout=20)
        except requests.RequestException as exc:
            print(f"  Request failed for {company_slug}/{metric_slug}: {exc}")
            return None

        if response.status_code != 200:
            print(f"  HTTP {response.status_code} for {company_slug}/{metric_slug}")
            return None

        return response.text

    def collect_company_filing_links(self, company_slug: str, page_metrics: list[str]) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []

        for page_metric in page_metrics:
            html = self._fetch_html(company_slug, page_metric)
            if not html:
                continue

            page_url = self.base_url.format(company=company_slug, metric=page_metric)
            all_rows.extend(extract_filing_links_from_html(html, page_url, page_metric))

        deduped: dict[str, dict[str, Any]] = {}
        for row in all_rows:
            deduped[row["file_url"]] = row

        return list(deduped.values())


def collect_filing_links(
    companies: list[tuple[str, str]],
    page_metrics: list[str],
) -> pd.DataFrame:
    scraper = CompaniesMarketCapFilingLinksScraper()
    rows: list[dict[str, Any]] = []

    for ticker, name in companies:
        company_slug = resolve_company_slug(ticker, name)
        print(f"Collecting filing links for {ticker} / {name} -> slug={company_slug}...")

        filing_rows = scraper.collect_company_filing_links(company_slug, page_metrics)
        print(f"  Found {len(filing_rows)} filing PDF links")

        if not filing_rows:
            rows.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "slug": company_slug,
                    "page_metric": "",
                    "report_type": "",
                    "page_url": "",
                    "file_url": "",
                    "file_name": "",
                    "report_year": pd.NA,
                    "source_href": "",
                    "status": "missing",
                }
            )
            continue

        for filing_row in filing_rows:
            rows.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "slug": company_slug,
                    **filing_row,
                    "status": "ok",
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "ticker",
                "name",
                "slug",
                "page_metric",
                "report_type",
                "page_url",
                "file_url",
                "file_name",
                "report_year",
                "source_href",
                "status",
            ]
        )

    df = pd.DataFrame(rows)
    df["report_year"] = pd.to_numeric(df["report_year"], errors="coerce")
    df = df.sort_values(["ticker", "report_year", "file_name"], ascending=[True, False, True], na_position="last")
    return df.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect CompaniesMarketCap annual filing PDF links")
    parser.add_argument("--ticker", help="Optional single ticker to collect")
    parser.add_argument("--max-companies", type=int, help="Optional cap for quick test runs")
    parser.add_argument(
        "--include-annual-reports",
        action="store_true",
        help="Also collect links from /annual-reports/ pages in addition to /annual-reports-10k/",
    )
    parser.add_argument(
        "--output",
        default="data/qvm/companiesmarketcap/companiesmarketcap_filing_links.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    base_dir = Path.cwd()
    input_csv = base_dir / "data" / "qvm" / "companies.csv"
    companies = load_companies(input_csv)

    if args.ticker:
        target = args.ticker.strip().upper()
        companies = [(ticker, name) for ticker, name in companies if ticker.upper() == target]
        if not companies:
            raise ValueError(f"Ticker not found in companies.csv: {target}")

    if args.max_companies is not None:
        companies = companies[: args.max_companies]

    page_metrics = ["annual-reports-10k"]
    if args.include_annual_reports:
        page_metrics.append("annual-reports")

    result = collect_filing_links(companies, page_metrics)

    output_path = (base_dir / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    ok_count = int((result["status"] == "ok").sum()) if not result.empty else 0
    missing_tickers = int((result["status"] == "missing").sum()) if not result.empty else 0
    coverage = 0.0
    if companies:
        covered = result.loc[result["status"] == "ok", "ticker"].nunique()
        coverage = covered / len(companies)

    print(f"Saved filing link index to {output_path}")
    print(f"Rows: {len(result)} | filing links: {ok_count} | companies without links: {missing_tickers} | ticker coverage: {coverage:.0%}")


if __name__ == "__main__":
    main()
