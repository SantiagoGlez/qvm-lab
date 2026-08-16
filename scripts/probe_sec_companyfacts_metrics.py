import argparse
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from quantlab.strategies.qvm.metrics.core import (
    compute_cash_total,
    compute_fcf_metrics,
    compute_invested_capital,
    compute_roic,
    compute_tax_rate,
)

try:
    from scripts.scrape_companiesmarketcap import load_companies
except ImportError:
    from scrape_companiesmarketcap import load_companies


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Candidate tags by priority.
TAG_CANDIDATES = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
        "PaymentsToAcquireProductiveAssets",
    ],
    "ebit": [
        "OperatingIncomeLoss",
    ],
    "interest_and_debt_expense": [
        "InterestAndDebtExpense",
        "InterestExpense",
        "InterestExpenseDebt",
    ],
    "tax_provision": [
        "IncomeTaxExpenseBenefit",
    ],
    "effective_tax_rate": [
        "EffectiveIncomeTaxRateContinuingOperations",
        "EffectiveIncomeTaxRateReconciliationAtFederalStatutoryIncomeTaxRate",
    ],
    "pretax_income": [
        "IncomeBeforeTax",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
    ],
    "short_term_investments": [
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesCurrent",
    ],
    "debt_total": [
        "DebtAndFinanceLeaseLiabilities",
        "LongTermDebtAndFinanceLeaseObligations",
        "DebtAndCapitalLeaseObligations",
        "LongTermDebt",
    ],
    "debt_current": [
        "DebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "FinanceLeaseLiabilityCurrent",
        "LongTermDebtCurrent",
    ],
    "debt_noncurrent": [
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
        "FinanceLeaseLiabilityNoncurrent",
        "LongTermDebtNoncurrent",
    ],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "TotalStockholdersEquity",
    ],
}

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
PREFERRED_UNITS = ("USD", "pure")

# Optional manual mapping for issuers that do not appear in SEC ticker datasets.
# Keep this intentionally small and only populate with verified CIK values.
SEC_CIK_OVERRIDES: dict[str, str] = {}

# Optional alternate SEC ticker symbols to try when local universe tickers differ.
SEC_TICKER_ALIASES: dict[str, list[str]] = {
    "MMC": ["MRSH"],
    "RNO": ["RNLSY", "RNSDF", "RNSDY"],
    "RHHBY": ["RHHBF"],
}


def _sec_headers() -> dict[str, str]:
    user_agent = os.getenv(
        "SEC_USER_AGENT",
        "qvm-lab-research/0.1 (contact: research@example.com)",
    )
    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


def _parse_accession_from_file_name(file_name: str) -> str | None:
    match = re.search(r"(\d{10}-\d{2}-\d{6})", file_name)
    if not match:
        return None
    return match.group(1)


def _fetch_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=_sec_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def _ticker_to_cik() -> dict[str, str]:
    payload = _fetch_json(SEC_TICKERS_URL)
    mapping: dict[str, str] = {}
    for _, row in payload.items():
        ticker = str(row.get("ticker", "")).upper().strip()
        cik_num = row.get("cik_str")
        if not ticker or cik_num is None:
            continue
        mapping[ticker] = f"{int(cik_num):010d}"
    return mapping


def _normalize_cik(value: str) -> str | None:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    return f"{int(digits):010d}"


def _resolve_cik_for_ticker(ticker: str, ticker_cik: dict[str, str]) -> tuple[str | None, str]:
    ticker_upper = ticker.upper().strip()

    override = SEC_CIK_OVERRIDES.get(ticker_upper)
    if override:
        normalized = _normalize_cik(override)
        if normalized:
            return normalized, f"override:{ticker_upper}"

    direct = ticker_cik.get(ticker_upper)
    if direct:
        return direct, f"ticker:{ticker_upper}"

    aliases = SEC_TICKER_ALIASES.get(ticker_upper, [])
    for alias in aliases:
        alias_upper = alias.upper().strip()
        cik = ticker_cik.get(alias_upper)
        if cik:
            return cik, f"alias:{ticker_upper}->{alias_upper}"

    return None, f"missing:{ticker_upper}"


def _load_filing_accessions(filing_links_csv: Path, ticker: str) -> set[str]:
    if not filing_links_csv.exists():
        return set()

    df = pd.read_csv(filing_links_csv)
    if df.empty:
        return set()

    filtered = df[(df.get("ticker") == ticker) & (df.get("status") == "ok")]
    if "report_type" in filtered.columns:
        filtered = filtered[filtered["report_type"] == "10k"]

    accessions: set[str] = set()
    if "file_name" not in filtered.columns:
        return accessions

    for file_name in filtered["file_name"].dropna().astype(str):
        accession = _parse_accession_from_file_name(file_name)
        if accession:
            accessions.add(accession)
    return accessions


def _iter_preferred_units(units: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[dict[str, Any]]]]:
    ordered: list[tuple[str, list[dict[str, Any]]]] = []
    seen: set[str] = set()

    for unit in PREFERRED_UNITS:
        values = units.get(unit)
        if values:
            ordered.append((unit, values))
            seen.add(unit)

    for unit in sorted(units):
        if unit in seen:
            continue
        values = units.get(unit)
        if values:
            ordered.append((unit, values))

    return ordered


def _extract_annual_facts(
    companyfacts: dict[str, Any],
    tag: str,
    allowed_accessions: set[str],
) -> dict[int, dict[str, Any]]:
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    tag_payload = us_gaap.get(tag, {})
    units = tag_payload.get("units", {})
    unit_values = _iter_preferred_units(units)

    by_year: dict[int, dict[str, Any]] = {}

    for unit, values in unit_values:
        for row in values:
            form = row.get("form")
            fp = row.get("fp")
            fy = row.get("fy")
            val = row.get("val")
            accn = row.get("accn")

            if form not in ANNUAL_FORMS:
                continue
            if fp != "FY":
                continue
            if fy is None or val is None:
                continue

            try:
                year = int(fy)
                number = float(val)
            except (TypeError, ValueError):
                continue

            existing = by_year.get(year)
            candidate = {
                "value": number,
                "accn": accn,
                "end": str(row.get("end") or ""),
                "tag": tag,
                "unit": unit,
                "accn_in_filing_links": bool(accn in allowed_accessions) if accn else False,
            }

            if existing is None:
                by_year[year] = candidate
                continue

            existing_is_linked = bool(existing.get("accn_in_filing_links"))
            candidate_is_linked = bool(candidate.get("accn_in_filing_links"))

            # Prefer the filing linked by our CompaniesMarketCap step-1 index.
            if candidate_is_linked and not existing_is_linked:
                by_year[year] = candidate
                continue

            if candidate_is_linked == existing_is_linked:
                # Then prefer latest fiscal end date.
                if candidate["end"] > str(existing.get("end") or ""):
                    by_year[year] = candidate

    return by_year


def _pick_series(
    companyfacts: dict[str, Any],
    metric_name: str,
    allowed_accessions: set[str],
) -> tuple[dict[int, dict[str, Any]], str | None]:
    merged: dict[int, dict[str, Any]] = {}
    first_tag: str | None = None

    for tag in TAG_CANDIDATES[metric_name]:
        series = _extract_annual_facts(companyfacts, tag, allowed_accessions)
        if not series:
            continue

        if first_tag is None:
            first_tag = tag

        # Priority order is the candidate list order: only backfill missing years.
        for year, payload in series.items():
            if year not in merged:
                merged[year] = payload

    return merged, first_tag


def _merge_year_values(
    metric_data: dict[str, tuple[dict[int, dict[str, Any]], str | None]],
) -> list[dict[str, Any]]:
    all_years: set[int] = set()
    for series, _ in metric_data.values():
        all_years.update(series.keys())

    rows: list[dict[str, Any]] = []
    for year in sorted(all_years, reverse=True):
        row: dict[str, Any] = {"year": year}
        for metric_name, (series, tag) in metric_data.items():
            value = series.get(year)
            row[metric_name] = value["value"] if value else None
            row[f"{metric_name}_tag"] = tag if value else None
            row[f"{metric_name}_accn"] = value.get("accn") if value else None
            row[f"{metric_name}_unit"] = value.get("unit") if value else None
            row[f"{metric_name}_linked_accn"] = value.get("accn_in_filing_links") if value else False
        rows.append(row)

    return rows


def _compute_derived(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)

        revenue = row.get("revenue")
        net_income = row.get("net_income")
        ocf = row.get("operating_cash_flow")
        capex = row.get("capex")
        ebit = row.get("ebit")
        tax = row.get("tax_provision")
        effective_tax_rate = row.get("effective_tax_rate")
        pretax = row.get("pretax_income")
        interest_and_debt_expense = row.get("interest_and_debt_expense")
        cash = row.get("cash")
        short_inv = row.get("short_term_investments")
        debt_total = row.get("debt_total")
        debt_current = row.get("debt_current")
        debt_noncurrent = row.get("debt_noncurrent")
        equity = row.get("equity")

        cash_total = compute_cash_total(cash=cash, short_term_investments=short_inv)

        if debt_total is not None:
            debt = float(debt_total)
        elif debt_current is not None or debt_noncurrent is not None:
            debt = float(debt_current or 0.0) + float(debt_noncurrent or 0.0)
        else:
            debt = None

        fcf, fcf_margin, fcf_conversion = compute_fcf_metrics(
            revenue=revenue,
            net_income=net_income,
            operating_cash_flow=ocf,
            capex=capex,
        )

        tax_rate = compute_tax_rate(
            tax_provision=tax,
            pretax_income=pretax,
            effective_tax_rate=effective_tax_rate,
        )

        ebit_for_roic = ebit
        ebit_proxy_from_pretax_interest = False
        if ebit_for_roic is None and pretax is not None and interest_and_debt_expense is not None:
            ebit_for_roic = float(pretax) + float(interest_and_debt_expense)
            ebit_proxy_from_pretax_interest = True

        invested_capital = compute_invested_capital(
            total_debt=debt,
            equity=equity,
            cash=cash,
            short_term_investments=short_inv,
        )

        roic = compute_roic(
            ebit=ebit_for_roic,
            invested_capital=invested_capital,
            tax_rate=tax_rate,
        )

        nopat = None
        if roic is not None and invested_capital is not None:
            nopat = roic * invested_capital

        enriched["cash_total"] = cash_total
        enriched["debt_computed"] = debt
        enriched["fcf_computed"] = fcf
        enriched["tax_rate_computed"] = tax_rate
        enriched["invested_capital_computed"] = invested_capital
        enriched["nopat_computed"] = nopat
        enriched["roic_computed"] = roic
        enriched["ebit_effective_for_roic"] = ebit_for_roic
        enriched["ebit_proxy_from_pretax_interest"] = ebit_proxy_from_pretax_interest
        enriched["fcf_margin_computed"] = fcf_margin
        enriched["fcf_conversion_computed"] = fcf_conversion

        enriched["has_roic_inputs"] = bool(ebit_for_roic is not None and tax_rate is not None and invested_capital not in (None, 0))
        enriched["has_fcf_inputs"] = bool(ocf is not None and capex is not None and revenue not in (None, 0) and net_income not in (None, 0))

        output.append(enriched)

    return output


def run_probe(
    ticker: str,
    filing_links_csv: Path,
    output_csv: Path,
    min_year: int | None = None,
    max_year: int | None = None,
) -> pd.DataFrame:
    ticker = ticker.upper().strip()
    ticker_cik = _ticker_to_cik()
    cik, cik_source = _resolve_cik_for_ticker(ticker, ticker_cik)
    if not cik:
        aliases = SEC_TICKER_ALIASES.get(ticker, [])
        alias_note = f" aliases_tried={aliases}" if aliases else ""
        raise ValueError(f"No CIK found for ticker: {ticker}.{alias_note}")

    accessions = _load_filing_accessions(filing_links_csv, ticker)

    companyfacts = _fetch_json(SEC_COMPANYFACTS_URL.format(cik=cik))

    metric_data: dict[str, tuple[dict[int, dict[str, Any]], str | None]] = {}
    for metric_name in TAG_CANDIDATES:
        metric_data[metric_name] = _pick_series(companyfacts, metric_name, accessions)

    rows = _merge_year_values(metric_data)
    rows = _compute_derived(rows)

    for row in rows:
        row["ticker"] = ticker
        row["cik"] = cik
        row["cik_source"] = cik_source
        row["accession_count_from_links"] = len(accessions)

    df = pd.DataFrame(rows)
    if df.empty:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_csv, index=False)
        return df

    if min_year is not None:
        df = df[df["year"] >= int(min_year)]
    if max_year is not None:
        df = df[df["year"] <= int(max_year)]

    df = df.sort_values("year", ascending=False).reset_index(drop=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    return df


def run_probe_bulk(
    tickers: list[str],
    filing_links_csv: Path,
    output_dir: Path,
    min_year: int | None = None,
    max_year: int | None = None,
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for ticker in tickers:
        ticker_upper = ticker.upper().strip()
        output_csv = output_dir / f"{ticker_upper.lower()}_sec_companyfacts_probe.csv"
        try:
            df = run_probe(
                ticker=ticker_upper,
                filing_links_csv=filing_links_csv,
                output_csv=output_csv,
                min_year=min_year,
                max_year=max_year,
            )
            years = len(df)
            roic_years = int(df["roic_computed"].notna().sum()) if not df.empty and "roic_computed" in df.columns else 0
            fcf_margin_years = int(df["fcf_margin_computed"].notna().sum()) if not df.empty and "fcf_margin_computed" in df.columns else 0
            fcf_conversion_years = int(df["fcf_conversion_computed"].notna().sum()) if not df.empty and "fcf_conversion_computed" in df.columns else 0
            rows.append(
                {
                    "ticker": ticker_upper,
                    "status": "ok",
                    "rows": years,
                    "roic_years": roic_years,
                    "fcf_margin_years": fcf_margin_years,
                    "fcf_conversion_years": fcf_conversion_years,
                    "error": "",
                }
            )
            print(
                f"[{ticker_upper}] rows={years} | ROIC={roic_years} | "
                f"FCF.Margin={fcf_margin_years} | FCF.Conv={fcf_conversion_years}"
            )
        except Exception as exc:
            rows.append(
                {
                    "ticker": ticker_upper,
                    "status": "error",
                    "rows": 0,
                    "roic_years": 0,
                    "fcf_margin_years": 0,
                    "fcf_conversion_years": 0,
                    "error": str(exc),
                }
            )
            print(f"[{ticker_upper}] error: {exc}")

    summary = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    return summary


def _print_summary(df: pd.DataFrame, ticker: str) -> None:
    if df.empty:
        print(f"No companyfacts rows available for {ticker}")
        return

    total_years = len(df)
    roic_years = int(df["roic_computed"].notna().sum())
    fcf_margin_years = int(df["fcf_margin_computed"].notna().sum())
    fcf_conversion_years = int(df["fcf_conversion_computed"].notna().sum())

    print(f"Years in probe: {total_years}")
    print(f"ROIC available years: {roic_years} ({(roic_years / total_years):.0%})")
    print(f"FCF Margin available years: {fcf_margin_years} ({(fcf_margin_years / total_years):.0%})")
    print(f"FCF Conversion available years: {fcf_conversion_years} ({(fcf_conversion_years / total_years):.0%})")

    cols = [
        "year",
        "revenue",
        "net_income",
        "operating_cash_flow",
        "capex",
        "ebit",
        "tax_provision",
        "pretax_income",
        "revenue_unit",
        "net_income_unit",
        "operating_cash_flow_unit",
        "capex_unit",
        "ebit_unit",
        "tax_provision_unit",
        "pretax_income_unit",
        "debt_computed",
        "cash_total",
        "invested_capital_computed",
        "roic_computed",
        "fcf_margin_computed",
        "fcf_conversion_computed",
    ]
    existing_cols = [col for col in cols if col in df.columns]
    print("\nSample rows:")
    print(df[existing_cols].head(8).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe SEC companyfacts for ROIC/FCF metric inputs")
    parser.add_argument("--ticker", help="Ticker symbol, e.g. MSFT")
    parser.add_argument("--all", action="store_true", help="Run probe for all tickers in data/qvm/companies.csv")
    parser.add_argument(
        "--filing-links-csv",
        default="data/qvm/companiesmarketcap/companiesmarketcap_filing_links.csv",
        help="Path to step-1 filing links CSV",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path. Defaults to data/qvm/companiesmarketcap/<ticker>_sec_companyfacts_probe.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="data/qvm/companiesmarketcap",
        help="Output directory used by --all for per-ticker probe files",
    )
    parser.add_argument(
        "--summary-output",
        default="data/qvm/companiesmarketcap/sec_companyfacts_probe_summary.csv",
        help="Summary CSV path used by --all",
    )
    parser.add_argument("--min-year", type=int, default=2010)
    parser.add_argument("--max-year", type=int, default=None)
    args = parser.parse_args()

    if not args.ticker and not args.all:
        parser.error("Provide --ticker <TICKER> or use --all")
    if args.ticker and args.all:
        parser.error("Use either --ticker or --all, not both")

    base_dir = Path.cwd()
    filing_links_csv = (base_dir / args.filing_links_csv).resolve()

    if args.all:
        companies_csv = base_dir / "data" / "qvm" / "companies.csv"
        companies = load_companies(companies_csv)
        tickers = [ticker for ticker, _ in companies]
        output_dir = (base_dir / args.output_dir).resolve()
        summary_output = (base_dir / args.summary_output).resolve()

        summary = run_probe_bulk(
            tickers=tickers,
            filing_links_csv=filing_links_csv,
            output_dir=output_dir,
            min_year=args.min_year,
            max_year=args.max_year,
        )
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(summary_output, index=False)

        ok = int((summary["status"] == "ok").sum())
        print(f"Saved bulk summary to {summary_output}")
        print(f"Bulk probe completed: {ok}/{len(summary)} tickers successful")
        return

    ticker = args.ticker.upper().strip()
    if args.output:
        output_csv = (base_dir / args.output).resolve()
    else:
        output_csv = (base_dir / "data" / "qvm" / "companiesmarketcap" / f"{ticker.lower()}_sec_companyfacts_probe.csv").resolve()

    df = run_probe(
        ticker=ticker,
        filing_links_csv=filing_links_csv,
        output_csv=output_csv,
        min_year=args.min_year,
        max_year=args.max_year,
    )

    print(f"Saved SEC probe output to {output_csv}")
    _print_summary(df, ticker)


if __name__ == "__main__":
    main()
