from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.probe_sec_companyfacts_metrics import _compute_derived, _extract_annual_facts, _parse_accession_from_file_name


def test_parse_accession_from_file_name() -> None:
    assert _parse_accession_from_file_name("0000950170-24-087843_msft-20240630.pdf") == "0000950170-24-087843"
    assert _parse_accession_from_file_name("1.ar.en.2024.pdf") is None


def test_compute_derived_uses_effective_tax_rate_fallback_for_roic() -> None:
    rows = [
        {
            "year": 2020,
            "revenue": 100.0,
            "net_income": 20.0,
            "operating_cash_flow": 30.0,
            "capex": 10.0,
            "ebit": 25.0,
            "tax_provision": None,
            "effective_tax_rate": 0.2,
            "pretax_income": None,
            "cash": 10.0,
            "short_term_investments": 5.0,
            "debt_total": 30.0,
            "debt_current": None,
            "debt_noncurrent": None,
            "equity": 70.0,
        }
    ]

    enriched = _compute_derived(rows)[0]

    assert enriched["tax_rate_computed"] == 0.2
    assert enriched["roic_computed"] is not None
    assert enriched["has_roic_inputs"] is True


def test_extract_annual_facts_falls_back_to_non_usd_units() -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "EUR": [
                            {
                                "form": "20-F",
                                "fp": "FY",
                                "fy": 2024,
                                "val": 123.0,
                                "accn": "0000000000-24-000001",
                                "end": "2024-12-31",
                            }
                        ]
                    }
                }
            }
        }
    }

    series = _extract_annual_facts(companyfacts, "NetCashProvidedByUsedInOperatingActivities", set())

    assert series[2024]["value"] == 123.0
    assert series[2024]["unit"] == "EUR"
