from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.scrape_companiesmarketcap_filing_links import (
    _extract_report_year,
    extract_filing_links_from_html,
)


def test_extract_report_year_prefers_four_digit_year() -> None:
    assert _extract_report_year("0000950170-24-087843_msft-20240630.pdf") == 2024
    assert _extract_report_year("1.ar.en.2023.pdf") == 2023
    assert _extract_report_year("0001193125-03-045632_d10k.pdf") == 2003
    assert _extract_report_year("no-year-here.pdf") is None


def test_extract_filing_links_filters_to_pdf_and_dedupes() -> None:
    html = """
    <a href=\"/annual-reports-10k/0000950170-24-087843_msft-20240630.pdf?save\">A</a>
    <a href=\"/annual-reports-10k/0000950170-24-087843_msft-20240630.pdf\">B</a>
    <a href=\"/annual-reports-10k/0000950170-23-035122_msft-20230630.pdf\">C</a>
    <a href=\"/microsoft/revenue/\">Not a filing</a>
    """

    rows = extract_filing_links_from_html(
        html=html,
        page_url="https://companiesmarketcap.com/microsoft/annual-reports-10k/",
        page_metric="annual-reports-10k",
    )

    assert len(rows) == 2
    assert rows[0]["report_type"] == "10k"
    assert rows[0]["file_url"].endswith(".pdf")
    assert all("annual-reports-10k" in row["file_url"] for row in rows)
    assert {row["report_year"] for row in rows} == {2023, 2024}
