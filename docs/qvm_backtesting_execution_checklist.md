# QVM Backtesting Execution Checklist (MVP)

## Status Tracking
- Status legend: Not Started | In Progress | Done | Blocked
- Last updated: YYYY-MM-DD

| Task | Status | Owner | Notes |
|---|---|---|---|
| BT-01 | Not Started | | |
| BT-02 | Not Started | | |
| BT-03 | Not Started | | |
| BT-04 | Not Started | | |
| BT-05 | Not Started | | |
| BT-06 | Not Started | | |
| BT-07 | Not Started | | |
| BT-08 | Not Started | | |
| BT-09 | Not Started | | |
| BT-10 | Not Started | | |
| BT-11 | Not Started | | |
| BT-12 | Not Started | | |
| BT-13 | Not Started | | |
| BT-14 | Not Started | | |
| BT-15 | Not Started | | |
| BT-16 | Not Started | | |

## Scope
- Objective: validate QVM Quality + Valuation process with historical inputs.
- Out of scope: momentum, execution realism, production-grade trading infra.

## Policies (Locked)
- Universe: current QVM universe (survivorship bias accepted).
- Rebalance: annual.
- Fundamentals timing: use Y-1 financials.
- Returns: Adjusted Close.
- Benchmark: SPY on same rebalance dates.
- Temporal invariant: no data newer than formation year is ever used.

## Task List

### BT-01: Module Skeleton
- Status: Not Started
- Create minimal historical backtest package and CLI entrypoint.
- Output contracts only (no business logic duplication).
- Acceptance:
  - Backtest command runs and returns structured placeholder output.

### BT-02: Historical Repository Interfaces
- Status: Not Started
- Define repository interfaces compatible with existing production services.
- Acceptance:
  - Types/models map directly to current valuation/quality service inputs.

### BT-03: Historical Valuation Repository
- Status: Not Started
- Read valuation CSVs and return PE history up to formation year.
- Add fallback behavior only if required by current data layout.
- Acceptance:
  - Unit tests prove cutoff correctness for multiple years.
  - No values newer than formation year are returned.

### BT-04: Historical Financial Repository
- Status: Not Started
- Read financial CSVs and expose Y-1 fundamentals for each formation year.
- Acceptance:
  - Unit tests confirm Y-1 behavior and year cutoff.
  - Missing data is explicit (not silently filled).

### BT-05: Temporal Integrity Guard
- Status: Not Started
- Add shared guard/check used by both repositories.
- Acceptance:
  - Negative tests fail when any post-cutoff row is present.
  - Guard is called in both repositories.

### BT-06: Historical Valuation Scoring Adapter
- Status: Not Started
- Feed historical valuation observations to existing valuation scoring logic.
- Acceptance:
  - Spot checks (MSFT, RHHBY, ADBE) match manual calculations for selected years.

### BT-07: Historical Quality Scoring Adapter
- Status: Not Started
- Feed historical Y-1 financials to existing quality scoring logic.
- Acceptance:
  - Scores vary by year as expected.
  - No formula duplication in historical layer.

### BT-08: Yearly QVM Scoring Pipeline
- Status: Not Started
- Build one pipeline call: company universe + formation year -> scored companies.
- Acceptance:
  - Output schema matches live structure (excluding momentum fields if omitted).

### BT-09: Eligibility Filter
- Status: Not Started
- Apply thresholds before ranking:
  - quality coverage >= 75%
  - historical PE observations >= 5
- Acceptance:
  - Ineligible companies are excluded with reason tags.

### BT-10: Ranking Stage
- Status: Not Started
- Reuse existing ranking logic for eligible companies only.
- Acceptance:
  - Deterministic ranking for repeated runs.
  - Tie handling follows existing logic.

### BT-11: Portfolio Construction
- Status: Not Started
- Equal-weight Top N, annual rebalance, 1-year hold.
- Acceptance:
  - Weights sum to 100% each year.
  - Holdings change only on rebalance dates.

### BT-12: Returns Engine
- Status: Not Started
- Compute annual portfolio returns from Adjusted Close.
- Compute annual SPY returns on same dates.
- Acceptance:
  - Portfolio and benchmark returns reconcile to source prices.

### BT-13: Metrics Engine
- Status: Not Started
- Compute: CAGR, annual returns, benchmark returns, excess return, max drawdown, volatility, Sharpe, win rate vs benchmark.
- Acceptance:
  - Metrics reconcile from annual return series.

### BT-14: Reporting
- Status: Not Started
- Produce concise yearly + summary report files.
- Include: formation year, selected holdings, portfolio return, benchmark return, excess return.
- Acceptance:
  - One command generates complete report artifacts in backtest output folder.

### BT-15: Test Suite and Invariants
- Status: Not Started
- Add layered tests for repositories, adapters, ranking, portfolio, metrics.
- Acceptance:
  - Cutoff invariant tests pass.
  - End-to-end sanity run (short window) passes in CI/local.

### BT-16: Execution Windows
- Status: Not Started
- Primary run: 2015-2025.
- Robustness run: 2019-2025.
- Acceptance:
  - Both windows run end-to-end without missing years.
  - Outputs are reproducible.

## Suggested Build Order
1. BT-01 to BT-05
2. BT-06 to BT-10
3. BT-11 to BT-14
4. BT-15 to BT-16

## Definition of Done (MVP)
- Historical backtest runs end-to-end for 2015-2025 and 2019-2025.
- Uses production valuation/quality logic with no duplicated formulas.
- Enforces temporal invariant and Y-1 policy.
- Produces reproducible rankings, returns, and summary metrics.
