# Google Finance Report QA Prompt (Quick Daily)

Use this prompt for a fast first-pass check before relying on a report.

## Prompt

Act as a strict QA checker for this stock report.
Do not give investment advice. Only validate facts, internal consistency, and logic.

Check in this order:
1. Data completeness: missing key fields (price, 52W high, SMA200, PE, leverage, growth, action rationale).
2. Math sanity: verify any computable percentages/ratios and sign conventions.
3. Signal consistency: trend/RS/pullback/assessment should not contradict each other.
4. Narrative fit: does the action and explanation match the actual numbers?
5. Business-type caveat: flag if cyclicality/defensive profile makes generic PE-momentum conclusions fragile.

Output exactly:
1. Verdict: Pass / Pass with Caveats / Fail
2. Top 3 Data Issues
3. Top 3 Logic Gaps
4. Confidence Score (0-100)
5. One-line Decision Safety: "Safe to use" or "Not safe to use"

Strict rule:
If missing data or key inconsistencies are material, output "Not safe to use".

Audit this report now:

[paste full company report here]
