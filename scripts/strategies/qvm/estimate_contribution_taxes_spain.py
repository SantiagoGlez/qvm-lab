from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


BRACKETS = [
    (6000.0, 0.19),
    (50000.0, 0.21),
    (200000.0, 0.23),
    (300000.0, 0.27),
    (float("inf"), 0.28),
]


def tax_on_net_gain(net_gain: float) -> float:
    if net_gain <= 0:
        return 0.0

    remaining = net_gain
    tax = 0.0
    for width, rate in BRACKETS:
        chunk = min(remaining, width)
        tax += chunk * rate
        remaining -= chunk
        if remaining <= 1e-12:
            break
    return tax


def sanitize_experiment_name(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_")


def replay_tax_for_experiment(
    *,
    experiment_dir: Path,
    allocation_policy: str,
    soft_trim_weight_cap: float,
    initial_contribution: float,
    recurring_contribution: float,
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    audit = pd.read_csv(experiment_dir / "audit.csv")
    years = sorted(audit["formation_year"].unique())

    shares: dict[str, float] = {}
    basis: dict[str, float] = {}

    yearly_rows: list[dict[str, float | int]] = []

    for index, year in enumerate(years):
        current = audit[audit["formation_year"] == year].sort_values("rank")
        selected = list(current["ticker"])
        transition_price = {row.ticker: float(row.buy_price) for row in current.itertuples(index=False)}

        forced_realized = 0.0
        cap_realized = 0.0

        previous_sell_price: dict[str, float] = {}
        if index > 0:
            previous_year = audit[audit["formation_year"] == (year - 1)]
            previous_sell_price = {
                row.ticker: float(row.sell_price) for row in previous_year.itertuples(index=False)
            }

        def sell_all_of_ticker(ticker: str, sale_price: float) -> float:
            quantity = shares.pop(ticker)
            avg_cost = basis.pop(ticker)
            return quantity * (sale_price - avg_cost)

        if allocation_policy in {"buy_biased_no_trim", "buy_biased_soft_cap"}:
            for ticker in list(shares.keys()):
                if ticker in selected:
                    continue
                sale_price = transition_price.get(ticker, previous_sell_price.get(ticker, 0.0))
                forced_realized += sell_all_of_ticker(ticker, sale_price)

        contribution = initial_contribution if index == 0 else recurring_contribution

        value_before = 0.0
        for ticker, quantity in shares.items():
            sale_price = transition_price.get(ticker, previous_sell_price.get(ticker, 0.0))
            value_before += quantity * sale_price

        cash = 0.0

        if allocation_policy == "reset_equal_weight":
            for ticker in list(shares.keys()):
                sale_price = transition_price.get(ticker, previous_sell_price.get(ticker, 0.0))
                quantity = shares[ticker]
                cash += quantity * sale_price
                forced_realized += sell_all_of_ticker(ticker, sale_price)

            total = cash + contribution
            per_name = total / len(selected) if selected else 0.0

            for ticker in selected:
                price = transition_price[ticker]
                shares[ticker] = per_name / price
                basis[ticker] = price

        else:
            for ticker in selected:
                shares.setdefault(ticker, 0.0)
                basis.setdefault(ticker, transition_price[ticker])

            if allocation_policy == "buy_biased_soft_cap" and value_before > 0 and selected:
                cap_value = value_before * soft_trim_weight_cap
                for ticker in selected:
                    quantity = shares.get(ticker, 0.0)
                    if quantity <= 0:
                        continue
                    price = transition_price[ticker]
                    position_value = quantity * price
                    excess_value = position_value - cap_value
                    if excess_value <= 0:
                        continue
                    quantity_to_sell = excess_value / price
                    shares[ticker] -= quantity_to_sell
                    cap_realized += quantity_to_sell * (price - basis[ticker])
                    cash += excess_value

            cash += contribution
            current_values = {
                ticker: shares.get(ticker, 0.0) * transition_price[ticker] for ticker in selected
            }
            total_value = cash + sum(current_values.values())
            target_value = total_value / len(selected) if selected else 0.0

            deficits = {
                ticker: max(0.0, target_value - current_values[ticker]) for ticker in selected
            }
            total_deficit = sum(deficits.values())

            if selected:
                if total_deficit <= 0:
                    allocation = {ticker: cash / len(selected) for ticker in selected}
                else:
                    allocation = {
                        ticker: cash * (deficits[ticker] / total_deficit)
                        for ticker in selected
                        if deficits[ticker] > 0
                    }

                spent = 0.0
                for ticker, amount in allocation.items():
                    if amount <= 0:
                        continue
                    price = transition_price[ticker]
                    quantity_bought = amount / price
                    old_quantity = shares.get(ticker, 0.0)
                    old_basis = basis.get(ticker, price)
                    new_quantity = old_quantity + quantity_bought
                    new_basis = (
                        ((old_quantity * old_basis) + amount) / new_quantity
                        if new_quantity > 0
                        else price
                    )
                    shares[ticker] = new_quantity
                    basis[ticker] = new_basis
                    spent += amount
                cash -= spent

        net_realized_gain = forced_realized + cap_realized
        estimated_tax = tax_on_net_gain(net_realized_gain)

        yearly_rows.append(
            {
                "year": int(year),
                "forced_realized_gain_eur": round(forced_realized, 2),
                "cap_realized_gain_eur": round(cap_realized, 2),
                "net_realized_gain_eur": round(net_realized_gain, 2),
                "estimated_tax_eur": round(estimated_tax, 2),
            }
        )

    yearly = pd.DataFrame(yearly_rows)
    summary = {
        "gross_realized_gain_eur": round(float(yearly["net_realized_gain_eur"].sum()), 2),
        "tax_eur_total": round(float(yearly["estimated_tax_eur"].sum()), 2),
        "taxable_years": int((yearly["net_realized_gain_eur"] > 0).sum()),
        "max_single_year_tax_eur": round(float(yearly["estimated_tax_eur"].max()), 2),
    }
    return yearly, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate Spanish capital gains tax from contribution experiment outputs.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("data/qvm/backtest/contribution_portfolio_taxaware"),
        help="Path containing contribution_experiment_comparison.csv and experiment subfolders.",
    )
    parser.add_argument("--initial-contribution", type=float, default=20000.0)
    parser.add_argument("--recurring-contribution", type=float, default=2000.0)
    args = parser.parse_args()

    comparison = pd.read_csv(args.base_dir / "contribution_experiment_comparison.csv")
    summary_rows: list[dict[str, object]] = []

    for row in comparison.itertuples(index=False):
        experiment_name = str(row.experiment)
        experiment_dir = args.base_dir / sanitize_experiment_name(experiment_name)

        yearly, totals = replay_tax_for_experiment(
            experiment_dir=experiment_dir,
            allocation_policy=str(row.allocation_policy),
            soft_trim_weight_cap=float(row.soft_trim_weight_cap),
            initial_contribution=args.initial_contribution,
            recurring_contribution=args.recurring_contribution,
        )

        yearly.to_csv(experiment_dir / "tax_yearly_estimate_spain.csv", index=False)

        final_value = float(row.final_value)
        total_contributions = float(row.total_contributions)

        summary_rows.append(
            {
                "experiment": experiment_name,
                "allocation_policy": row.allocation_policy,
                "turnover": round(float(row.turnover), 4),
                "portfolio_twr_cagr": round(float(row.twr_cagr), 4),
                "spy_twr_cagr": round(float(row.benchmark_twr_cagr), 4),
                "excess_twr_cagr": round(float(row.excess_twr_cagr), 4),
                "portfolio_mwrr": round(float(row.mwrr), 4),
                "spy_mwrr": round(float(row.benchmark_mwrr), 4),
                "excess_mwrr": round(float(row.excess_mwrr), 4),
                "final_value": round(final_value, 4),
                "spy_final_value": round(float(row.benchmark_final_value), 4),
                "total_contributions": round(total_contributions, 4),
                **totals,
                "after_tax_final_value": round(final_value - totals["tax_eur_total"], 4),
                "tax_pct_of_final_value": round(totals["tax_eur_total"] / final_value, 6) if final_value > 0 else 0.0,
                "tax_pct_of_contributions": round(totals["tax_eur_total"] / total_contributions, 6)
                if total_contributions > 0
                else 0.0,
            }
        )

    summary = pd.DataFrame(summary_rows).sort_values("tax_eur_total")
    output_path = args.base_dir / "tax_and_returns_with_spy.csv"
    summary.to_csv(output_path, index=False)
    summary.to_csv(args.base_dir / "tax_estimate_spain_comparison.csv", index=False)

    print(summary.to_string(index=False))
    print(f"\nWrote {output_path}")


if __name__ == "__main__":
    main()
