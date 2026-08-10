from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_marketcap import audit_directory, audit_file, classify_confidence


def test_audit_file_reports_counts_and_warnings(tmp_path: Path) -> None:
    csv_path = tmp_path / "test_valuation.csv"
    pd.DataFrame(
        {
            "Year": [2020, 2021, 2022, 2023, 2024],
            "revenue": [10.0, 12.0, 0.0, 14.0, 15.0],
            "net_income": [1.0, 2.0, None, -1.0, 3.0],
            "pe_ratio": [20.0, -5.0, 0.0, 25.0, None],
            "cash": [1.0, 2.0, 3.0, None, 5.0],
            "total_assets": [10.0, 11.0, 12.0, 13.0, 14.0],
            "dividend_yield": [None, None, None, None, None],
        }
    ).to_csv(csv_path, index=False)

    report = audit_file(csv_path, ticker="TEST")

    assert report["rows"] == 5
    assert report["years"] == (2020, 2024)
    assert report["duplicates"] == 0
    assert report["pe_history"]["valid"] == 4
    assert report["pe_history"]["missing"] == 1
    assert report["pe_history"]["negative"] == 1
    assert report["pe_history"]["zero"] == 1
    assert report["missing_values"]["revenue"] == 0
    assert report["missing_values"]["net_income"] == 1
    assert report["missing_values"]["dividend_yield"] == 5
    assert report["revenue"]["negative"] == 0
    assert report["revenue"]["zero"] == 1
    assert report["net_income"]["missing"] == 1
    assert report["net_income"]["negative"] == 1
    assert report["filtering"]["raw_pe"] == 4
    assert report["filtering"]["used"] == 4
    assert report["recent_window"]["pe_missing"] == 1
    assert report["recent_window"]["net_income_missing"] == 1
    assert classify_confidence(report) == "LOW"


def test_audit_directory_writes_bulk_report(tmp_path: Path) -> None:
    csv_a = tmp_path / "aaa_test_valuation.csv"
    csv_b = tmp_path / "bbb_test_valuation.csv"
    output_path = tmp_path / "bulk_audit.txt"

    for path in (csv_a, csv_b):
        pd.DataFrame(
            {
                "Year": [2020, 2021],
                "revenue": [10.0, 11.0],
                "net_income": [1.0, 2.0],
                "pe_ratio": [20.0, 21.0],
                "cash": [1.0, 2.0],
                "total_assets": [10.0, 11.0],
                "dividend_yield": [None, None],
            }
        ).to_csv(path, index=False)

    written_path = audit_directory(tmp_path, output_path=output_path)

    assert written_path == output_path
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "CompaniesMarketCap Audit" in content
    assert "AAA" in content or "BBB" in content
