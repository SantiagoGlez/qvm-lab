# Historical Backtesting Plan

# Overview

The objective is to validate the QVM investment strategy using only information that would have been available at each point in time.

This is **not** intended to become a generic trading framework. The goal is to build the simplest possible backtesting engine that answers:

> Would our Quality + Valuation investment process have produced attractive long-term results?

The implementation should remain modular and reuse the production scoring logic wherever possible.

---

# Business Rules for the Initial Backtester

The first implementation should deliberately stay narrow and avoid scope creep. The backtester is validating the QVM process, not the entire market-engineering stack.

## Rule 1 — No future data leakage

For a formation year Y, all inputs must be restricted to data available on or before the end of year Y.

Examples:

- valuation history can only include PE observations from years <= Y
- financial metrics can only use annual figures filed or effectively known by Y
- portfolio results for a formation year must only use scores computed from that historical snapshot
- no use of later returns, later rating changes, or current market conditions when forming the portfolio

This rule is the single most important guardrail. If it is violated, the test no longer represents a valid historical strategy.

## Rule 2 — Formation year defines the investment snapshot

The historical backtester should treat the formation year as the date of portfolio creation.

At that point:

- the universe is built from companies that exist and have usable data as of that date
- each company receives a score using only historical values up to that date
- the ranking is computed solely from the historical QVM score at that snapshot

The purpose is to simulate an investor making decisions at the start of each year based on the information available then.

## Rule 3 — Production scoring logic is reused; only the data source changes

Historical components are adapters. They do not redefine valuation or quality formulas.

The historical layer must expose the same interfaces expected by production services, so the live formula implementation remains the source of truth.

The backtester must not copy or re-implement:

- valuation scoring
- quality scoring
- percentile logic
- score thresholds
- band assignments

This keeps the historical engine consistent with the production process and avoids silent drift between live and historical logic.

## Rule 4 — Momentum is excluded from the first pass

For the initial implementation, the backtester should ignore momentum/market-assessment signals entirely.

This means:

- the ranking is based on Quality + Valuation only
- no trend, relative strength, or pullback filters are used
- the backtester is designed to evaluate the core QVM investment process before adding timing effects

This is intentional: the goal is to validate whether the quality-and-valuation framework itself has long-term merit.

## Rule 5 — Portfolio construction is deliberately simple

The first portfolio engine will be intentionally minimal:

- equal weight
- buy top N names
- hold for one year
- annual rebalance
- ignore taxes, trading costs, shorting, cash management, and position sizing complexity

This keeps the first implementation focused on whether the strategy works in principle rather than on execution realism.

## Rule 6 — Annual performance must be measured from the actual portfolio snapshot

Each year should produce a single portfolio built from the formation-year ranking. That portfolio is then held for the next 12 months, and the yearly return is computed against the next-year value.

This means:

- no overlap between the formation-year data and post-formation-year measurement beyond the actual held period
- the return for each portfolio is measured against the same calendar interval used to define the hold period
- annual results are aggregated into CAGR, drawdown, volatility, Sharpe, and benchmark excess return later

## Rule 7 — Universe membership and ranking are snapshot-based, not ex-post filtered

When building a ranked universe for formation year Y:

- you are allowed to include only companies that had data available as of Y
- you cannot choose winners based on later outcomes
- the same company list should be reproducible for a given historical snapshot

This makes the ranking auditable and prevents hindsight bias.

## Rule 8 — The historical engine is a thin adapter, not a separate strategy definition

The historical layer is responsible only for:

- reading data from historical CSVs or archives
- filtering to the requested year
- returning the same data models used by the live services

It is not responsible for creating new formulas, thresholds, or strategy heuristics.

This is the cleanest way to keep historical backtests honest and maintainable.

---

# Design Principle

Historical backtesting must reuse the existing production business logic.

The historical components are responsible only for exposing historical data filtered to a requested formation year.

The existing services should continue to own:

- valuation calculations
- quality calculations
- scoring thresholds
- business rules

There should be a single implementation of every formula.

The only difference between Live and Historical execution is the data source.

Data Integrity Invariant:

- Historical repositories must never return data newer than the requested formation year.

```
Live

Current Data
        ↓
Production Services
        ↓
Scores
```

```
Historical

Historical Data (up to formation year)
        ↓
Production Services
        ↓
Scores
```

---

# Backtest Policy

The following policy choices are fixed for the MVP to keep the implementation focused and reproducible:

- Universe: use the current QVM universe. Survivorship bias is acknowledged and accepted as an MVP limitation.
- Formation date: annual rebalance.
- Fundamental data timing: use previous fiscal year financials (Y-1) for each formation year to avoid look-ahead bias.
- Returns: use Adjusted Close prices (dividends and splits included).
- Benchmark: SPY with the same rebalance dates.

---

# Step 1 — Historical Data Adapters

## Goal

Implement historical data providers that expose historical information using the interfaces expected by the production services.

Examples:

```
HistoricalValuationRepository

HistoricalFinancialRepository
```

Responsibilities:

- read historical valuation CSVs
- read historical financial CSVs
- expose only data available up to the requested formation year
- return the same models used by the production services whenever possible

No scoring logic should be duplicated.

## Verification

Verify that:

- repositories never return data newer than the requested formation year
- data integrity invariant is enforced: repositories never return records newer than the requested formation year
- repositories correctly filter by formation year
- returned objects can be consumed directly by existing services

---

# Step 2 — Historical Valuation

## Goal

Reuse the existing valuation implementation.

The historical layer should provide the historical PE observations while the existing ValuationService performs all calculations.

No valuation formulas should be copied.

## Verification

Validate several companies:

- Microsoft
- Roche
- Adobe

Confirm:

- Average PE
- Median PE
- Percentile
- Valuation Score

match manual calculations using only historical observations.

---

# Step 3 — Historical Quality

## Goal

Reuse the existing QualityService.

Historical repositories provide historical financial metrics.

The production QualityService computes:

- ROE
- ROIC
- Growth
- Financial Strength
- Quality Score

without modification.

## Verification

Validate multiple companies across multiple formation years.

Confirm:

- no data newer than the requested formation year is used
- quality evolves consistently
- coverage behaves as expected

---

# Step 4 — Historical QVM

## Goal

Reuse the existing QVM pipeline.

The only difference should be that inputs come from historical repositories.

Output should be identical in structure to the live strategy.

## Verification

Compare historical runs for recent years with the live implementation.

Business logic should produce identical results when given identical inputs.

---

# Step 5 — Historical Universe Ranking

## Goal

Generate the ranked investment universe for any formation year.

Example:

```
Formation Year 2018

1 Microsoft

2 Visa

3 Adobe

...
```

Reuse the existing ranking logic whenever possible.

## Eligibility Rules

- Minimum Quality Coverage: 70%.
- Minimum Historical PE observations: 5.
- Companies not meeting these thresholds are excluded from that formation year's ranking.
- Existing ranking logic remains unchanged for eligible companies.

## Verification

Confirm:

- rankings use historical scores only
- no data newer than the requested formation year is used
- scores are reproducible

---

# Step 6 — Simple Portfolio Engine

## Goal

Implement the simplest possible portfolio simulation.

Rules:

- Equal weight
- Buy Top N companies
- Hold for one year
- Annual rebalance

Ignore for now:

- Momentum
- Transaction costs
- Taxes
- Position sizing
- Cash management

The objective is to validate the investment process rather than execution realism.

## Verification

Check:

- Top N holdings
- Equal weights
- Correct annual rebalances

---

# Step 7 — Annual Backtest Engine

## Goal

Run the yearly simulation.

```
Formation Year

↓

Historical Scores

↓

Rank Companies

↓

Build Portfolio

↓

Hold One Year

↓

Measure Performance

↓

Repeat
```

Initial period:

```
2015 → 2025
```

Later perform a robustness check:

```
2019 → 2025
```

## Verification

Confirm:

- one portfolio per year
- no missing years
- no data newer than each requested formation year is used
- annual returns reconcile correctly

---

# Step 8 — Performance Metrics

Compute only the core metrics.

Required:

- CAGR
- Annual Returns
- Benchmark Returns
- Excess Return
- Maximum Drawdown
- Volatility
- Sharpe Ratio
- Win Rate vs Benchmark

## Verification

Validate that reported metrics reconcile with yearly portfolio values.

---

# Step 9 — Reporting

Produce a concise report.

Example:

```
Formation Year: 2018

Top 10

MSFT

V

ADBE

...

Portfolio Return

18.4%

Benchmark

13.1%

Excess Return

+5.3%
```

Final Summary:

- CAGR
- Sharpe
- Volatility
- Maximum Drawdown
- Years Outperforming Benchmark

## Verification

Review manually.

Confirm rankings, returns and metrics are internally consistent.

---

# Guiding Principles

- Reuse production business logic whenever possible.
- Historical code should provide historical data, not duplicate scoring algorithms.
- Keep each component focused on a single responsibility.
- Avoid parallel implementations of formulas.
- Validate every step independently before proceeding.
- Build the smallest backtester capable of answering whether the QVM investment process has long-term merit.

---

# MVP Simplifications

The following exclusions are intentional in the first implementation:

- Historical universe reconstruction (survivorship bias).
- SEC filing calendars and exact publication dates.
- Transaction costs.
- Slippage.
- Taxes.
- Liquidity constraints.
- Sector neutrality.

These are conscious design decisions to keep the first implementation focused on validating the investment process rather than building a production-grade backtesting framework.