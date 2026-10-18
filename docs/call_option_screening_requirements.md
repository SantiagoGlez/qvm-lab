# Call option screening requirements

## Goal
Build a feature to identify which universe stocks are suitable for covered or directional call options with expiries of 6, 9, and 12 months.

## Requirements
- Score each stock in the current universe using the existing QVM quality, intrinsic valuation, historical valuation, and market signals.
- Treat intrinsic valuation as the primary valuation lens for call candidates, with historical valuation used as a confirmation check.
- Filter out names with weak fundamentals, very expensive historical valuation, poor market trend, or low-quality growth.
- Rank candidates separately for 6M, 9M, and 12M call horizons.
- Prefer names with strong quality, positive trend, reasonable intrinsic setup, and supportive market assessment.
- Penalize stocks with extremely high implied volatility, weak liquidity, or poor options market quality.
- Output a ranked shortlist with a score, rationale, and expiry recommendation.
- Keep the feature compatible with the current project architecture and data pipeline.

## Implementation plan
1. Reuse the existing `analyse_company()` flow to evaluate each universe ticker.
2. Build a new call-screening module that reads the analysed company objects.
3. Add a baseline filter using quality, intrinsic assessment, historical valuation, and market trend thresholds.
4. Add a horizon-specific scoring model for 6M, 9M, and 12M.
5. Add optional option-market checks: IV, liquidity, volume, and open interest when available.
6. Score and rank candidates separately for each expiry bucket.
7. Add a CLI command to print the recommended candidates for a selected maturity.
8. Validate with a quick smoke test using a few known universe stocks and a manual sanity check of the output.

## Trade recommendation layer

The stock-level screen is only the first stage. A real call recommendation must also define the actual option trade.

### Required trade inputs
- ticker
- trade thesis
- recommended expiry (6, 9, or 12 months)
- strike selection logic
- approximate delta target
- risk budget
- break-even level
- target exit level
- stop-loss / max loss threshold
- liquidity check on the option chain

### Trade quality requirements
- The underlying must pass the conservative screening criteria.
- The option must have sufficient open interest and trading volume.
- The selected strike must not be excessively far out-of-the-money unless the thesis is very strong.
- Risk must be capped to a predefined loss budget.
- Entry must require a clear trigger, such as price holding a key support level or momentum staying positive.

### Recommended execution rules
- Prefer liquid, standard strikes with adequate open interest.
- Prefer a maturity that matches the thesis horizon and the market regime.
- Avoid recommending calls when IV is extreme or when liquidity is weak.
- Keep the recommendation directional and time-aware; do not treat the screen as a guaranteed buy signal.
- Always document the thesis and the risk/reward structure before executing.

## Notes
- Intrinsic valuation should be weighted more heavily than historical valuation for call screening.
- Historical valuation remains useful as a confirmation layer, especially to avoid expensive setups.
- This should be layered on top of the existing QVM analysis, not a replacement.
- The first version can be conservative and rely on underlying quality before adding deep options analytics.
- The option layer should remain optional and degrade gracefully when no option data is available.
- The recommendation layer should be treated as a second-stage decision process built on top of the screening layer.
