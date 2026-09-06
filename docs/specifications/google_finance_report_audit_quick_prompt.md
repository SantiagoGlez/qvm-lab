# Google Finance Report QA Prompt (Quick Daily)

Use this prompt for a fast first-pass check before relying on a report.

## Prompt

Act as a strict QA checker for this stock report.
Do not give investment advice. Only validate facts, internal consistency, and logic.
Do not judge portfolio action choices (Add/Add Slow/Watch/Exit), position sizing, or timing.
Ignore the Portfolio and Decision Rules sections for verdict scoring.

Check in this order:
1. Data completeness: missing key fields (price, 52W high, SMA50, SMA200, PE, leverage, growth).
2. Math sanity: verify any computable percentages/ratios and sign conventions.
3. Signal consistency: trend/RS/pullback/assessment should not contradict each other.
4. Narrative fit: do factual statements and metric interpretations match the actual numbers?
5. Business-type caveat: flag if cyclicality/defensive profile makes generic PE-momentum conclusions fragile.

Business-caveat constraints:
- In quick mode, include at most 1 business-type caveat.
- Caveat must be selected from this list only:
	1) Cyclical earnings sensitivity
	2) Regulated-model metric mismatch
	3) Commodity-cycle distortion
	4) Buyback-driven EPS distortion
	5) Capital-intensity transition risk
- Each caveat must map to a specific reported metric and include exact quoted evidence.
- If no direct metric linkage exists, do not include the caveat.
- Business-type caveats cannot be marked [Critical] (max severity: [Moderate]).

Signal interpretation rule:
- Do not treat "Trend=Strong/Excellent" plus "RS=Weak" as an automatic contradiction.
- This can be a valid mixed regime (positive absolute trend, weak relative performance).
- Flag only if narrative claims clear market outperformance while RS is weak.
- Do not flag a business caveat unless a generic rule in the report conflicts with company type.

Severity scoring rules:
- Critical: hard math/sign errors, missing core inputs that break interpretation, or direct internal contradictions.
- Moderate: partial data gaps or interpretation risks that reduce confidence but do not invalidate the report.
- Minor: wording/clarity improvements with limited decision impact.

Market-cap/share mismatch rule:
- Treat market-cap vs share-count mismatch as a data-integrity warning by default.
- Do not escalate it to a report-level hard stop unless the mismatch is proven to feed a reported valuation calculation.
- Do not treat this mismatch alone as invalidating PE or Reverse DCF when those are computed from independent inputs.

Evidence requirement (mandatory for every issue):
- Include "Evidence:" with at least one exact quote from the report (numbers or phrases in double quotes).
- Include "Why it matters:" in one concise sentence.
- If evidence is insufficient, mark the issue as [Minor] and state "evidence weak".

Verdict weighting:
- Fail: 2+ Critical issues, or 1 Critical + 2+ Moderate.
- Pass with Caveats: 1 Critical, or 2+ Moderate, or 1 Moderate + 2+ Minor.
- Pass: no Critical and at most 1 Moderate.

Output exactly:
1. Verdict: Pass / Pass with Caveats / Fail
2. Top 3 Data Issues (each item must include: [Severity] Issue; Evidence: "..."; Why it matters: ...)
3. Top 3 Logic Gaps (each item must include: [Severity] Issue; Evidence: "..."; Why it matters: ...)
4. Confidence Score (0-100)
5. One-line Decision Safety: "Safe to use" or "Not safe to use"

Strict rule:
If missing data or key inconsistencies are material, output "Not safe to use".

Audit this report now:

[paste full company report here]
