from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import time
from typing import Literal


AuditMode = Literal["quick", "full"]


@dataclass(slots=True)
class GoogleFinanceChatResult:
    success: bool
    response: str
    prompt: str
    error: str = ""


_QUICK_AUDIT_PROMPT = """Act as a strict QA checker for this stock report.
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
5. One-line Decision Safety: Safe to use or Not safe to use

Strict rule:
If missing data or key inconsistencies are material, output Not safe to use.
"""


_FULL_AUDIT_PROMPT = """You are an independent QA auditor for equity reports.
Your primary goal is to find data-quality issues and logic gaps before validating conclusions.

Important:
1. First audit data reliability and consistency.
2. Only then audit interpretation and recommendations.
3. Be skeptical and explicit.
4. Do not provide investment advice.
5. If data is weak, say the report is not decision-grade.

Audit workflow (must follow in order)

Phase 1: Data Integrity Audit
1. Check whether key inputs are present and internally consistent.
2. Recompute obvious ratios where possible and compare to reported values.
3. Identify stale-data risk, mixed-frequency risk, and source-mismatch risk.
4. Flag sign-convention ambiguity.
5. Output a Data Quality Grade: A, B, C, or D.

Phase 2: Business-Model Context Audit
1. Determine if the company appears cyclical, secular growth, defensive, regulated, or commodity-linked.
2. Check whether the report logic is appropriate for that type.
3. Flag where generic rules may mislead for this business model.

Phase 3: Logic and Narrative Audit
1. Check if conclusions match the facts.
2. Detect contradictions across dimensions.
3. Flag overconfident wording not supported by data.
4. Distinguish hard errors from soft gaps.

Phase 4: Decision-Grade Verdict
Return exactly:
1. Overall Verdict: Pass / Pass with Caveats / Fail
2. Data Issues (highest priority)
3. Logic Gaps
4. Business-Model Fit Check
5. Minimum Fixes Before Trusting This Report
6. Confidence Score (0-100)

Strict rule:
If Data Quality Grade is C or D, explicitly state:
Do not rely on this report for action decisions until data issues are fixed.
"""


def build_google_finance_audit_prompt(report_text: str, mode: AuditMode = "quick") -> str:
    header = _FULL_AUDIT_PROMPT if mode == "full" else _QUICK_AUDIT_PROMPT
    return f"{header}\n\nAudit this report now:\n\n{report_text.strip()}\n"


def _try_load_prompt_from_docs(mode: AuditMode) -> str | None:
    root = Path(__file__).resolve().parents[5]
    file_name = (
        "google_finance_report_audit_full_prompt.md"
        if mode == "full"
        else "google_finance_report_audit_quick_prompt.md"
    )
    prompt_path = root / "docs" / "specifications" / file_name
    if not prompt_path.exists():
        return None
    text = prompt_path.read_text(encoding="utf-8")
    marker = "## Prompt"
    if marker not in text:
        return None
    return text.split(marker, 1)[1].strip()


def build_google_finance_audit_prompt_from_docs_or_default(
    report_text: str,
    mode: AuditMode = "quick",
) -> str:
    prompt_body = _try_load_prompt_from_docs(mode)
    if prompt_body is None:
        return build_google_finance_audit_prompt(report_text, mode=mode)

    # Keep only the instruction part from docs; remove placeholder sections.
    for marker in ("Audit this report now:", "[paste full company report here]"):
        if marker in prompt_body:
            prompt_body = prompt_body.split(marker, 1)[0].strip()

    return f"{prompt_body}\n\nAudit this report now:\n\n{report_text.strip()}\n"


def _split_issue_lines(block: str) -> list[str]:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    issues: list[str] = []
    current: str | None = None
    for line in lines:
        normalized = line.lstrip("-• ").strip()
        if not normalized:
            continue

        looks_new = (
            normalized.lower().startswith(("missing ", "no ", "net ", "sign ", "trend ", "action ", "expectation "))
            or ":" in normalized
            or re.match(r"^\d+[\.)]\s+", normalized) is not None
        )
        if looks_new:
            if current:
                issues.append(current.strip())
            current = re.sub(r"^\d+[\.)]\s*", "", normalized)
        elif current is None:
            current = normalized
        else:
            current = f"{current} {normalized}"

    if current:
        issues.append(current.strip())

    seen: set[str] = set()
    unique_issues: list[str] = []
    for issue in issues:
        key = issue.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_issues.append(issue)
    return unique_issues


def _extract_section(text: str, headers: list[str], next_headers: list[str]) -> str:
    lower_text = text.lower()
    start = -1
    matched_header = ""
    for header in headers:
        idx = lower_text.find(header.lower())
        if idx != -1 and (start == -1 or idx < start):
            start = idx
            matched_header = header
    if start == -1:
        return ""

    content_start = start + len(matched_header)
    block = text[content_start:]
    if block.startswith(":"):
        block = block[1:]
    block = block.lstrip()

    end = len(block)
    lower_block = block.lower()
    for header in next_headers:
        idx = lower_block.find(header.lower())
        if idx != -1:
            end = min(end, idx)
    return block[:end].strip()


def format_google_finance_audit_response(raw_response: str) -> str:
    text = raw_response.strip()
    if not text:
        return ""

    verdict_anchor = re.search(r"(?:Overall\s+)?Verdict\s*:?\s*", text, flags=re.IGNORECASE)
    if verdict_anchor and verdict_anchor.start() > 0:
        text = text[verdict_anchor.start():].strip()

    verdict_match = re.search(
        r"(?:\d+\.\s*)?(?:Overall\s+)?Verdict\s*:?\s*(Pass with Caveats|Pass|Fail)",
        text,
        flags=re.IGNORECASE,
    )
    verdict = verdict_match.group(1) if verdict_match else "Unknown"

    data_block = _extract_section(
        text,
        headers=["Top 3 Data Issues", "Data Issues"],
        next_headers=["Top 3 Logic Gaps", "Logic Gaps", "Confidence Score", "One-line Decision Safety", "Decision Safety"],
    )
    logic_block = _extract_section(
        text,
        headers=["Top 3 Logic Gaps", "Logic Gaps"],
        next_headers=["Confidence Score", "One-line Decision Safety", "Decision Safety"],
    )

    data_issues = _split_issue_lines(data_block)[:3] if data_block else []
    logic_gaps = _split_issue_lines(logic_block)[:3] if logic_block else []

    confidence_match = re.search(r"Confidence\s*Score\s*:?\s*(\d{1,3})", text, flags=re.IGNORECASE)
    confidence = confidence_match.group(1) if confidence_match else "N/A"

    safety_match = re.search(
        r"(?:One-line\s+)?Decision\s+Safety\s*:?\s*\"?([^\n\"]+)\"?",
        text,
        flags=re.IGNORECASE,
    )
    safety = safety_match.group(1).strip() if safety_match else "Unknown"

    material_terms = (
        "missing",
        "contradict",
        "inconsisten",
        "error",
        "ambigu",
        "wrong",
        "mismatch",
        "omitted",
    )
    has_material_blocker = any(
        term in issue.lower() for issue in (data_issues + logic_gaps) for term in material_terms
    )
    safety_overridden = False
    if has_material_blocker and "safe to use" in safety.lower() and "not safe" not in safety.lower():
        safety = "Not safe to use"
        safety_overridden = True

    lines: list[str] = []
    lines.append(f"Verdict: {verdict}")
    lines.append("")
    lines.append("Material Data Issues")
    if data_issues:
        for idx, issue in enumerate(data_issues, start=1):
            lines.append(f"{idx}. {issue}")
    else:
        lines.append("1. None clearly identified.")

    lines.append("")
    lines.append("Logic Gaps")
    if logic_gaps:
        for idx, gap in enumerate(logic_gaps, start=1):
            lines.append(f"{idx}. {gap}")
    else:
        lines.append("1. None clearly identified.")

    lines.append("")
    lines.append(f"Decision Safety: {safety}")
    lines.append(f"Confidence Score: {confidence}")
    lines.append("Confidence Meaning: confidence refers to certainty in identified QA issues, not return potential.")
    if safety_overridden:
        lines.append("Safety Rule Applied: marked Not safe to use because material blockers were detected.")
    return "\n".join(lines).strip()


def fetch_google_finance_beta_chat_response(
    prompt: str,
    *,
    timeout_seconds: int = 120,
    headless: bool = True,
) -> str:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError(
            "Playwright is not installed. Install with 'uv add playwright' and "
            "then run 'playwright install chromium'."
        ) from exc

    def _dump_debug_artifacts(page, reason: str) -> Path:
        root = Path(__file__).resolve().parents[5]
        debug_dir = root / "data" / "qvm" / "google_finance_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        run_dir = debug_dir / f"run_{stamp}"
        run_dir.mkdir(parents=True, exist_ok=True)

        (run_dir / "reason.txt").write_text(reason, encoding="utf-8")
        (run_dir / "url.txt").write_text(page.url, encoding="utf-8")
        try:
            (run_dir / "title.txt").write_text(page.title(), encoding="utf-8")
        except Exception:
            pass

        try:
            page.screenshot(path=str(run_dir / "page.png"), full_page=True)
        except Exception:
            pass

        try:
            (run_dir / "page.html").write_text(page.content(), encoding="utf-8")
        except Exception:
            pass

        return run_dir

    def _dismiss_possible_consent(page) -> None:
        consent_selectors = [
            'button:has-text("I agree")',
            'button:has-text("Accept all")',
            'button:has-text("Accept")',
            'button:has-text("Agree")',
            '[aria-label*="Accept"]',
        ]
        for selector in consent_selectors:
            button = page.locator(selector).first
            if button.count() == 0:
                continue
            try:
                button.click(timeout=1000)
            except Exception:
                continue

    def _find_input_locator(page):
        # Prefer explicit chat-style textarea/contenteditable fields.
        input_selectors = [
            'textarea[aria-label*="Ask"]',
            'textarea[placeholder*="Ask"]',
            'textarea[aria-label*="chat" i]',
            'textarea[placeholder*="chat" i]',
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
            'textarea',
            'input[type="text"]',
        ]
        for selector in input_selectors:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=2000)
                return locator
            except PlaywrightTimeoutError:
                continue
        return None

    def _extract_candidate_response(page) -> str:
        def _clean(text: str) -> str:
            cleaned = text.strip()
            verdict_anchor = re.search(r"(?:Overall\s+)?Verdict\s*:?\s*", cleaned, flags=re.IGNORECASE)
            if verdict_anchor and verdict_anchor.start() > 0:
                cleaned = cleaned[verdict_anchor.start():]
            for marker in (
                "AI responses may include mistakes",
                "Help",
                "Send feedback",
                "Privacy",
                "Terms",
                "Disclaimer",
                "Ask a follow-up question",
                "Voice Search",
                "Add Tool",
                "Ask AI",
                "prompt_suggestion",
            ):
                idx = cleaned.find(marker)
                if idx != -1:
                    cleaned = cleaned[:idx].strip()

            cleaned = re.sub(
                r"\\n[A-Za-z0-9 .,&'\\-]+\\n1D\\n5D\\n1M\\n6M\\nYTD\\n1Y\\n5Y\\nMAX\\s*$",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            cleaned = re.sub(
                r"\\n1D\\s*\\n5D\\s*\\n1M\\s*\\n6M\\s*\\nYTD\\s*\\n1Y\\s*\\n5Y\\s*\\nMAX\\b.*$",
                "",
                cleaned,
                flags=re.IGNORECASE | re.DOTALL,
            ).strip()
            return cleaned

        # Variant: structured QA card where headings are split, e.g.
        # "1. Verdict" on one line and "Pass with Caveats" on the next line.
        try:
            card_locator = page.locator("div.DR1ox")
            card_count = min(card_locator.count(), 8)
        except Exception:
            card_count = 0

        for idx in range(card_count):
            card = card_locator.nth(idx)
            try:
                card_text = card.inner_text(timeout=1200).strip()
            except Exception:
                continue
            if not card_text:
                continue
            lower = card_text.lower()
            if "audit this report now" in lower:
                continue
            if "pass / pass with caveats / fail" in lower:
                continue

            has_verdict_block = bool(
                re.search(
                    r"(?:\d+\.\s*)?(?:overall\s+)?verdict\s*:?\s*(pass with caveats|pass|fail)",
                    lower,
                    flags=re.IGNORECASE,
                )
                or (
                    "1. verdict" in lower
                    and re.search(r"\b(pass with caveats|pass|fail)\b", lower) is not None
                )
            )
            if not has_verdict_block:
                continue

            if "top 3 data issues" not in lower and "data issues" not in lower:
                continue

            cleaned = _clean(card_text)
            if len(cleaned) >= 40:
                return cleaned

        # Finance beta currently renders assistant output in a structured ordered
        # list container (`ol.ObvqKe`) under `div.DR1ox`.
        try:
            verdict_lists = page.locator("ol.ObvqKe")
            count = verdict_lists.count()
        except Exception:
            count = 0

        for idx in range(count):
            item = verdict_lists.nth(idx)
            try:
                text = item.inner_text(timeout=1000).strip()
            except Exception:
                continue
            if not text:
                continue
            lower = text.lower()
            if "verdict:" not in lower:
                continue
            if "pass / pass with caveats / fail" in lower:
                # Prompt template block, not model output.
                continue

            try:
                container = item.locator('xpath=ancestor::div[contains(@class,"DR1ox")][1]').first
                container_text = container.inner_text(timeout=1000).strip()
            except Exception:
                container_text = text

            cleaned = _clean(container_text)
            if len(cleaned) >= 40:
                return cleaned

        response_selectors = [
            '[data-message-author-role="assistant"]',
            '[data-testid*="assistant"]',
            '[role="article"]',
            'main [class*="response"]',
            'main [class*="answer"]',
            'main [class*="message"]',
        ]
        texts: list[str] = []
        for selector in response_selectors:
            locator = page.locator(selector)
            count = 0
            try:
                count = min(locator.count(), 8)
            except Exception:
                continue
            for idx in range(count):
                try:
                    text = locator.nth(idx).inner_text(timeout=800).strip()
                except Exception:
                    continue
                if not text:
                    continue
                if "Audit this report now" in text:
                    continue
                if len(text) < 50:
                    continue
                texts.append(_clean(text))
        if not texts:
            # Fallback: some Finance beta layouts render chat in custom panels
            # without stable assistant-role selectors. Extract from visible body text.
            try:
                body_text = page.locator("body").inner_text(timeout=1200)
            except Exception:
                return ""

            # Quick prompt expected section.
            # Accept only concrete verdict outcomes, not template text.
            verdict_matches = list(
                re.finditer(
                    r"1\.\s*Verdict\s*:?\s*(Pass with Caveats|Pass|Fail)",
                    body_text,
                    flags=re.IGNORECASE,
                )
            )
            overall_matches = list(
                re.finditer(
                    r"1\.\s*Overall Verdict\s*:?\s*(Pass with Caveats|Pass|Fail)",
                    body_text,
                    flags=re.IGNORECASE,
                )
            )

            all_matches = verdict_matches + overall_matches
            if not all_matches:
                return ""

            start_idx = max(m.start() for m in all_matches)
            candidate = body_text[start_idx:]

            # Template guardrail: if the block still includes instruction template,
            # do not treat it as a valid assistant response.
            if "Pass / Pass with Caveats / Fail" in candidate:
                return ""

            end_markers = [
                "Ask a follow-up question",
                "Help",
                "Send feedback",
                "AI content may include mistakes",
                "expand_more",
                "Voice Search",
                "Add Tool",
                "Ask AI",
            ]
            end_idx = len(candidate)
            for marker in end_markers:
                idx = candidate.find(marker)
                if idx != -1:
                    end_idx = min(end_idx, idx)

            candidate = _clean(candidate[:end_idx].strip())
            return candidate if len(candidate) >= 40 else ""
        # Heuristic: assistant response is usually the longest substantial message.
        return sorted(texts, key=len)[-1]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            page.goto(
                "https://www.google.com/finance/beta?hl=en",
                wait_until="domcontentloaded",
                timeout=timeout_seconds * 1000,
            )
            _dismiss_possible_consent(page)

            input_locator = _find_input_locator(page)

            if input_locator is None:
                debug_dir = _dump_debug_artifacts(page, "Could not find chat input")
                raise RuntimeError(
                    "Could not find Google Finance chat input on the page. "
                    f"Debug artifacts: {debug_dir}"
                )

            input_locator.click()
            try:
                input_locator.fill(prompt)
            except Exception:
                page.keyboard.type(prompt)

            sent = False
            send_selectors = [
                'button[aria-label*="Send"]',
                'button:has-text("Send")',
                'button[data-testid*="send"]',
                '[role="button"][aria-label*="Submit"]',
            ]
            for selector in send_selectors:
                button = page.locator(selector).first
                if button.count() == 0:
                    continue
                try:
                    button.click(timeout=1500)
                    sent = True
                    break
                except Exception:
                    continue

            if not sent:
                page.keyboard.press("Enter")

            deadline = time.monotonic() + timeout_seconds
            response_text = ""
            # Wait until we find a substantive assistant response.
            while time.monotonic() < deadline:
                response_text = _extract_candidate_response(page)
                if response_text:
                    break
                page.wait_for_timeout(750)

            if not response_text:
                debug_dir = _dump_debug_artifacts(page, "Could not capture assistant response")
                raise RuntimeError(
                    "Could not capture assistant response from Google Finance page. "
                    f"Debug artifacts: {debug_dir}"
                )

            return response_text
        finally:
            browser.close()


def run_google_finance_audit(
    report_text: str,
    *,
    mode: AuditMode = "quick",
    timeout_seconds: int = 120,
    headless: bool = True,
) -> GoogleFinanceChatResult:
    prompt = build_google_finance_audit_prompt_from_docs_or_default(report_text, mode=mode)

    try:
        response = fetch_google_finance_beta_chat_response(
            prompt,
            timeout_seconds=timeout_seconds,
            headless=headless,
        )
        formatted_response = format_google_finance_audit_response(response)
        return GoogleFinanceChatResult(success=True, response=formatted_response, prompt=prompt)
    except Exception as exc:
        return GoogleFinanceChatResult(success=False, response="", prompt=prompt, error=str(exc))
