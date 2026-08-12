from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.probe_sec_companyfacts_metrics import (
    _compute_derived,
    _extract_annual_facts,
    _parse_accession_from_file_name,
    _resolve_cik_for_ticker,
)


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


def test_compute_derived_reconstructs_ebit_from_pretax_and_interest() -> None:
    rows = [
        {
            "year": 2020,
            "revenue": 100.0,
            "net_income": 20.0,
            "operating_cash_flow": 30.0,
            "capex": 10.0,
            "ebit": None,
            "tax_provision": 5.0,
            "effective_tax_rate": None,
            "pretax_income": 25.0,
            "interest_and_debt_expense": 3.0,
            "cash": 10.0,
            "short_term_investments": 0.0,
            "debt_total": 30.0,
            "debt_current": None,
            "debt_noncurrent": None,
            "equity": 70.0,
        }
    ]

    enriched = _compute_derived(rows)[0]

    assert enriched["ebit_effective_for_roic"] == 28.0
    assert enriched["ebit_proxy_from_pretax_interest"] is True
    assert enriched["roic_computed"] is not None
    assert enriched["has_roic_inputs"] is True


def test_resolve_cik_for_ticker_direct_match() -> None:
    cik, source = _resolve_cik_for_ticker("MSFT", {"MSFT": "0000789019"})

    assert cik == "0000789019"
    assert source == "ticker:MSFT"


def test_resolve_cik_for_ticker_alias_match() -> None:
    cik, source = _resolve_cik_for_ticker("RNO", {"RNLSY": "0000123456"})

    assert cik == "0000123456"
    assert source == "alias:RNO->RNLSY"
