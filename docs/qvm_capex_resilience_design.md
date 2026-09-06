# QVM Capex Resilience Design

## Purpose

Add a small intrinsic-analysis overlay that answers one question:

> If the current elevated investment cycle fails to generate the expected returns, how resilient is the company's cash generation?

This is intentionally narrower than a full driver-based FCF model.

The first goal is not to forecast upside precisely. The first goal is to explain downside resilience in capital-intensive periods.

## Business Rationale

The existing QVM company report already has a useful expectations lens through Reverse DCF:

- Reverse DCF asks what FCF growth the market is pricing in.

What is missing is a paired downside lens:

- If elevated capex disappoints, how much of current cash generation remains?

That makes Capex Resilience a complement to Reverse DCF rather than a replacement for valuation, quality, or growth analysis.

Recommended scope:

- Apply only to selected companies where capex intensity is materially elevated.
- Keep it out of QVM scoring initially.
- Optimize for clear report output, not a complex model.

## Existing Architecture Anchors

The current codebase already provides the main integration points needed for this overlay.

### Current report assembly

- `analyse_company()` in `src/quantlab/strategies/qvm/service.py` orchestrates provider loading, scoring, market analysis, and portfolio action.
- `print_report()` in `src/quantlab/strategies/qvm/reports/console.py` renders the intrinsic analysis as a dedicated report section.

### Current intrinsic analysis pattern

- `src/quantlab/strategies/qvm/intrinsic/reverse_dcf.py` defines a focused analytical service and input dataclass.
- `src/quantlab/strategies/qvm/models.py` stores the result under `Company.reverse_dcf`.
- Reverse DCF is already treated as an explanatory layer rather than a scoring factor.

### Current data already available

From live analysis in `src/quantlab/strategies/qvm/providers/yahoo.py`:

- Current revenue-adjacent fundamentals
- TTM free cash flow
- Market cap, shares, balance-sheet fields
- Annual cash-flow statement fields sufficient to derive FCF

From historical backtest data in `src/quantlab/strategies/qvm/historical/repositories.py`:

- `operating_cash_flow`
- `capex`
- `free_cash_flow`
- `revenue_by_year`
- `fcf_by_year`

From shared helpers in `src/quantlab/strategies/qvm/metrics/core.py`:

- FCF derivation logic
- Net cash logic

## Design Principles

1. Keep the overlay independent from QVM scores and ranking.
2. Reuse the intrinsic-analysis pattern already established by Reverse DCF.
3. Prefer reported cash-flow facts over assumption-heavy decompositions.
4. Distinguish clearly between observed data and analytical stress assumptions.
5. Make the output readable in one screen section of the company report.

## Proposed Capability

Capex Resilience should answer three layers of questions.

### 1. Relevance

Is the current capex cycle elevated enough that a stress overlay is worth showing?

### 2. Current burden

How much of the company's operating cash generation is currently being consumed by investment?

### 3. Failure scenario

If capex above the company's historical normal level earns zero return, what residual FCF remains?

## Proposed Module Design

Keep the first implementation parallel to Reverse DCF.

```text
src/quantlab/strategies/qvm/
  intrinsic/
    capex_resilience.py
```

The first version should contain:

- `CapexResilienceInputs`
- `CapexResilienceAnalysis`
- `CapexResilienceService`

This keeps the overlay self-contained and minimizes accidental coupling to scoring logic.

## Proposed Model Additions

Add a new result model to `src/quantlab/strategies/qvm/models.py` and store it on `Company`.

### New analysis model

Suggested shape:

```python
class CapexResilienceAnalysis(BaseModel):
    relevance: str = "Not Material"
    relevance_reason: str | None = None

    current_revenue: float | None = None
    current_operating_cash_flow: float | None = None
    current_capex: float | None = None
    current_free_cash_flow: float | None = None
    net_cash: float | None = None

    capex_to_revenue: float | None = None
    capex_to_cfo: float | None = None
    fcf_margin: float | None = None
    net_cash_to_capex: float | None = None

    historical_capex_to_revenue_median: float | None = None
    historical_years_used: int = 0
    excess_capex: float | None = None
    excess_capex_to_revenue: float | None = None

    stress_free_cash_flow: float | None = None
    stress_fcf_margin: float | None = None
    stress_fcf_impact: float | None = None
    stress_fcf_impact_pct: float | None = None

    resilience: str = "Unavailable"
    resilience_reason: str | None = None

    operating_cash_flow_source: str = "Unavailable"
    capex_source: str = "Unavailable"
    revenue_source: str = "Unavailable"
    history_source: str = "Unavailable"
```

### Company integration

Suggested field on `Company`:

```python
capex_resilience: CapexResilienceAnalysis = Field(default_factory=CapexResilienceAnalysis)
```

This mirrors the existing `reverse_dcf` pattern and keeps report rendering straightforward.

## Input Contract

The service should take a narrow input shape similar to Reverse DCF.

```python
@dataclass(slots=True)
class CapexResilienceInputs:
    revenue: float | None
    operating_cash_flow: float | None
    capex: float | None
    free_cash_flow: float | None
    net_cash: float | None

    revenue_by_year: dict[int, float]
    operating_cash_flow_by_year: dict[int, float]
    capex_by_year: dict[int, float]
    free_cash_flow_by_year: dict[int, float]

    revenue_source: str = "Unavailable"
    operating_cash_flow_source: str = "Unavailable"
    capex_source: str = "Unavailable"
    free_cash_flow_source: str = "Unavailable"
    history_source: str = "Unavailable"
```

Only `revenue_by_year` and `capex_by_year` are required for the normal-capex baseline. `operating_cash_flow_by_year` and `free_cash_flow_by_year` are still worth carrying because they improve report transparency and future extension options.

## Core Service Logic

The first service should remain simple and deterministic.

### Step 1. Relevance detection

Mark the overlay as relevant only when capex looks materially elevated.

Initial rule set:

- `capex_to_revenue >= 0.10`, or
- `capex_to_cfo >= 0.50`, or
- `capex_to_revenue - historical_capex_to_revenue_median >= 0.03`

The higher standalone `capex_to_cfo` gate is intentional. In live samples, a lower threshold created false positives for low-capex businesses with naturally higher capex-to-CFO ratios, such as retail names with routine reinvestment.

These thresholds should be constants in the service, not hardcoded into the report.

If not relevant:

- return `relevance = "Not Material"`
- still populate observed metrics when possible
- skip stress classification if the signal is clearly immaterial

### Step 2. Current burden metrics

Compute:

- `capex_to_revenue = abs(capex) / revenue`
- `capex_to_cfo = abs(capex) / operating_cash_flow`
- `fcf_margin = free_cash_flow / revenue`
- `net_cash_to_capex = net_cash / abs(capex)` when meaningful

Use absolute capex because financial statements often report capex as a negative cash-flow number.

### Step 3. Historical normal capex

Compute a baseline from available historical years:

- `historical_capex_to_revenue_median = median(abs(capex_y) / revenue_y)`

Rules:

- Prefer a 5Y median when at least 5 valid observations exist.
- Fall back to a shorter median when at least 3 valid observations exist.
- If fewer than 3 observations exist, degrade gracefully and mark history quality as limited through `relevance_reason` or `resilience_reason`.

Then estimate:

- `normal_capex = revenue * historical_capex_to_revenue_median`
- `excess_capex = max(0.0, abs(capex) - normal_capex)`

This preserves the intended business logic: only capex above the normal maintenance burden is stressed.

### Step 4. Failed incremental capex scenario

Base stress assumption:

> Excess capex above the historical norm generates zero incremental economic return.

Implementation shortcut for MVP:

- `stress_free_cash_flow = free_cash_flow - excess_capex`

This is conservative and easy to explain. It should be documented explicitly as a stress simplification, not a literal accounting restatement.

Derived outputs:

- `stress_fcf_impact = stress_free_cash_flow - free_cash_flow`
- `stress_fcf_impact_pct = stress_fcf_impact / abs(free_cash_flow)` when possible
- `stress_fcf_margin = stress_free_cash_flow / revenue`

### Step 5. Resilience classification

Keep the label simple.

Initial classification proposal:

- `High`
  - stress FCF remains positive, and
  - stress FCF margin remains healthy, and
  - capex burden is moderate or balance sheet is strong
- `Moderate`
  - stress FCF remains positive but meaningfully compressed
- `Low`
  - stress FCF approaches zero or turns negative, or
  - capex consumes a very large share of CFO with little balance-sheet cushion
- `Unavailable`
  - key data missing

Do not convert this into a numeric score in V1.

## Reuse vs New Code

### Reuse directly

- `compute_fcf_metrics()` in `src/quantlab/strategies/qvm/metrics/core.py`
- `compute_net_cash()` in `src/quantlab/strategies/qvm/metrics/core.py`
- report integration pattern from `src/quantlab/strategies/qvm/intrinsic/reverse_dcf.py`
- company assembly in `src/quantlab/strategies/qvm/service.py`
- historical financial repository in `src/quantlab/strategies/qvm/historical/repositories.py`

### Add new code

- `src/quantlab/strategies/qvm/intrinsic/capex_resilience.py`
- new analysis model in `src/quantlab/strategies/qvm/models.py`
- provider plumbing to build `CapexResilienceInputs`
- report rendering section in `src/quantlab/strategies/qvm/reports/console.py`
- backtest repository payload extensions only if later needed for historical replay

## Provider Integration Design

### Live company flow

Add capex resilience assembly inside `YahooProvider.load()` after the existing cash-flow extraction and before returning `Company`.

This is the cleanest location because that provider already has access to:

- current revenue
- current operating cash flow
- current capex
- current free cash flow
- annual history extraction logic
- net cash inputs

Recommended internal helper methods:

- `_annual_operating_cash_flow_series(stock)`
- `_annual_capex_series(stock)`
- `_build_capex_resilience_inputs(...)`

This avoids pushing raw extraction logic into the intrinsic service.

### Backtest flow

Do not include backtest support in the first implementation unless specifically needed.

The current business case is a report overlay for selected companies, not a ranking feature.

If backtest support is later requested, extend:

- `CompaniesMarketCapHistoricalFinancialRepository.load()`

to emit:

- `operating_cash_flow_by_year`
- `capex_by_year`

and add a helper parallel to `_build_reverse_dcf_inputs()` in `src/quantlab/strategies/qvm/backtest/annual.py`.

## Report Integration

Add a new subsection under `Intrinsic Valuation` in `src/quantlab/strategies/qvm/reports/console.py`.

Recommended order:

1. Reverse DCF
2. Capex Resilience

That preserves the narrative:

- What growth is the market requiring?
- What happens if current elevated investment disappoints?

Suggested report layout:

```text
Capex Resilience

  Relevance                High
  Relevance Reason         Capex/revenue is 22.7%, 7.1pp above 5Y median.

Current Burden

  Capex / Revenue          22.7%
  Capex / CFO              55.5%
  FCF Margin               18.2%
  Net Cash / Capex         1.8x

Historical Baseline

  Historical Capex/Rev     15.6% (5Y median)
  Excess Capex             $15.0B

Failed Incremental Capex

  Stress FCF Impact        -$15.0B
  Stress FCF               $10.0B
  Stress FCF Margin        10.0%

Assessment

  High

Notes

  - Stress assumes capex above historical normal level produces no incremental return.
  - This is an analytical downside overlay, not a forecast or score.
```

If not relevant, show a short version:

```text
Capex Resilience

  Relevance                Not Material
  Note                     Current capex does not appear materially elevated versus the company's normal range.
```

## Recommended Implementation Stages

### Stage 1. Data model and formula service

Deliverables:

- `CapexResilienceAnalysis` model
- `CapexResilienceInputs` dataclass
- `CapexResilienceService`
- unit tests for formulas and edge cases

Tests should cover:

- capex sign handling
- insufficient history
- no-excess-capex case
- negative FCF case
- strong net-cash company
- low-resilience company

### Stage 2. Live provider integration

Deliverables:

- live extraction of annual capex and CFO history in `YahooProvider`
- assembly of `company.capex_resilience`
- graceful fallback behavior when data is partial

Success criteria:

- report can populate the overlay for a handful of target companies
- missing inputs degrade to `Unavailable` or `Not Material` rather than crashing

### Stage 3. Report rendering

Deliverables:

- new console report section
- short narrative note when relevant
- concise note when not material

Success criteria:

- section is legible and does not overwhelm the current report
- the distinction between observed metrics and stress assumption is explicit

### Stage 4. Historical replay support

Optional.

Deliverables:

- repository payload support for `operating_cash_flow_by_year` and `capex_by_year`
- helper in backtest annual scoring path
- smoke tests for historical assembly

This stage should only be done if you want historical report reconstruction or later validation across a larger sample.

## Testing Plan

### Formula tests

Add tests under:

- `tests/formulas/test_capex_resilience.py`

Focus on service behavior only.

### Provider tests

If provider logic is split into helper methods, add targeted tests or small fakes around extracted annual series assembly.

### Report tests

Add a rendering-oriented test only if the repo already treats report formatting as a stable interface. Otherwise prefer formula and model tests.

## Architectural Risks

### 1. Data extraction duplication

`YahooProvider` already mixes data fetching, series extraction, and analysis assembly. Adding another overlay there increases coupling.

Mitigation:

- move capex-resilience input assembly into small provider helper methods
- keep classification logic inside the intrinsic service, not the provider

### 2. Weak historical cash-flow provenance

Historical revenue and FCF are already handled more explicitly than historical CFO and capex.

Mitigation:

- treat V1 as live-report focused
- defer backtest/historical replay support until needed

### 3. False precision

Users may over-read a stress output as a formal forecast.

Mitigation:

- label it clearly as a downside stress overlay
- keep the assumptions minimal and disclosed

### 4. Threshold drift

If thresholds live in report code, service code, and portfolio code independently, behavior will drift.

Mitigation:

- centralize all Capex Resilience thresholds in the service module

## Explicit Non-Goals for V1

- No maintenance-vs-growth capex decomposition
- No AI-capex identification from reported numbers
- No incremental ROIC engine
- No scenario tree beyond the single failed-incremental-capex stress
- No QVM score contribution
- No portfolio action rule changes

## Recommended Next Step

Implement Stage 1 through Stage 3 only.

That gives the company report a practical new intrinsic lens at low complexity:

- Reverse DCF: what growth is priced in?
- Capex Resilience: what if elevated investment disappoints?

This is the highest business-value path before revisiting a broader driver-based FCF architecture.