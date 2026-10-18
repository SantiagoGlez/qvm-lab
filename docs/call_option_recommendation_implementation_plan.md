# Call Option Recommendation Implementation Plan

## Goal
Create a practical recommendation layer on top of the QVM call-screening feature so the system can move from a ranked shortlist of names to a trade-level call recommendation.

## Scope
Phase 1: screening layer
- identify candidate stocks for 6M, 9M, and 12M horizons
- keep the logic conservative
- filter on quality, intrinsic valuation, market trend, and action
- optionally penalize IV, volume, and open interest

Phase 2: recommendation layer
- choose the best call trade idea from each screened candidate
- define trade thesis, strike, expiry, risk, and exit rules
- validate liquidity and execution quality
- output a structured trade recommendation instead of only a stock shortlist

## Design principles
- Keep the underlying stock screen as the primary gate.
- Treat option data as a secondary adjustment, not the main decision driver.
- Favor high-quality, improving, reasonably valued names.
- Require a clear risk budget and execution rule for any call recommendation.
- Prefer transparency and explainability over complex option-modeling shortcuts.

## Implementation steps

### 1. Extend the screening module
- Confirm the base eligibility model is already working.
- Add a dedicated function to return the top candidate list by maturity.
- Keep the score formula interpretable and easy to tune.

### 2. Add a recommendation builder
- For each screened ticker, build a call recommendation object.
- Inputs:
  - ticker
  - quality score
  - intrinsic assessment
  - historical valuation
  - market assessment
  - maturity
  - trade thesis
  - risk budget
  - target and stop

### 3. Add option-chain enrichment
- Load option data if available.
- Validate at least:
  - liquidity
  - open interest
  - bid-ask spread
  - IV level
- Reject or down-rank candidates whose option chain is weak.

### 4. Define the trade decision rules
- Recommended strike selection should be based on a defined distance from the current price.
- Preferred maturity should align with the thesis horizon.
- Delta should remain in a target range to keep the recommendation controlled.
- Break-even and max loss must be explicit.

### 5. Add a human-readable recommendation output
Output a table or structured summary with columns like:
- ticker
- maturity
- thesis
- current price
- suggested strike
- delta band
- break-even
- max loss
- target
- risk level
- confidence

### 6. Add execution criteria
A call recommendation should only be emitted when:
- the stock passes the screening gate
- the option is liquid enough
- the thesis remains intact
- the risk is within budget
- the candidate still satisfies the maturity selection rules

### 7. Add tests
- screening test: high-quality candidates pass, weak candidates fail
- recommendation test: valid candidate becomes a structured trade recommendation
- liquidity test: weak option chain is rejected or downgraded
- maturity test: 6/9/12 months are returned correctly based on config

### 8. Add CLI support
- Extend the current CLI with a recommendation mode
- Example usage:
  - qvm-call-screen --months 9
  - qvm-call-reco --months 9 --top 5
- Keep the base screening command and the recommendation command distinct

## Suggested rule thresholds
Start conservative:
- quality score >= 70
- intrinsic assessment not overly optimistic
- historical valuation not expensive
- market trend not weak
- portfolio action not reject/exit
- option liquidity and OI must be acceptable
- avoid extreme IV unless explicitly part of a thesis

## Recommended first milestone
Implement the recommendation layer only after the screening layer is stable and verified. The first milestone should be:

1. screen valid candidates
2. enrich with option liquidity data
3. generate a structured recommendation object
4. print a simple trade summary in the CLI

## Success criteria
The feature is considered ready when:
- the screening layer is stable and explainable
- the recommendation layer generates trade-level output
- weak option chains are filtered out
- the output is actionable for a human analyst
- both the screening test and recommendation test pass
