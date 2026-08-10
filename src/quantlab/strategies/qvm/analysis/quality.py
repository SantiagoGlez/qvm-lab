from ..models import AnalysisResult, Company


def pct(value: float | None) -> str:
    """Format a float as a percentage."""
    if value is None:
        return "-"
    return f"{value:.1%}"


def num(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def recommendation(score: float) -> str:
    if score >= 90:
        return "Excellent"

    if score >= 75:
        return "Good"

    if score >= 60:
        return "Average"

    return "Weak"


def _score_roe(roe: float | None) -> float:

    if roe is None:
        return 0

    roe *= 100

    if roe >= 30:
        return 100

    if roe >= 20:
        return 85

    if roe >= 15:
        return 70

    if roe >= 10:
        return 50

    return 25


def _score_gross_margin(margin: float | None) -> float:

    if margin is None:
        return 0

    margin *= 100

    if margin >= 70:
        return 100

    if margin >= 50:
        return 85

    if margin >= 35:
        return 70

    if margin >= 20:
        return 50

    return 25


def _score_operating_margin(margin: float | None) -> float:

    if margin is None:
        return 0

    margin *= 100

    if margin >= 30:
        return 100

    if margin >= 20:
        return 85

    if margin >= 15:
        return 70

    if margin >= 10:
        return 50

    return 25


def _score_roic(roic: float | None) -> float:
    if roic is None:
        return 0

    roic *= 100

    if roic >= 25:
        return 100

    if roic >= 15:
        return 85

    if roic >= 10:
        return 70

    if roic >= 5:
        return 50

    return 25


def _score_cagr(cagr: float | None) -> float:
    if cagr is None:
        return 0

    cagr *= 100

    if cagr >= 20:
        return 100

    if cagr >= 15:
        return 85

    if cagr >= 10:
        return 70

    if cagr >= 5:
        return 50

    if cagr >= 0:
        return 25

    return 0


def _score_fcf_margin(margin: float | None) -> float:
    if margin is None:
        return 0

    margin *= 100

    if margin >= 20:
        return 100

    if margin >= 15:
        return 85

    if margin >= 10:
        return 70

    if margin >= 5:
        return 50

    if margin >= 0:
        return 25

    return 0


def _score_fcf_conversion(conversion: float | None) -> float:
    if conversion is None:
        return 0

    conversion *= 100

    if conversion >= 100:
        return 100

    if conversion >= 80:
        return 85

    if conversion >= 60:
        return 70

    if conversion >= 40:
        return 50

    if conversion >= 0:
        return 25

    return 0


def _score_net_debt_ebitda(ratio: float | None) -> float:
    """Lower (or negative) is better: negative ratio means net cash position."""
    if ratio is None:
        return 0

    if ratio <= 0:
        return 100  # net cash

    if ratio <= 0.5:
        return 85

    if ratio <= 1.5:
        return 70

    if ratio <= 3.0:
        return 50

    return 25


def _score_interest_coverage(coverage: float | None) -> float:
    if coverage is None:
        return 0

    if coverage >= 15:
        return 100

    if coverage >= 10:
        return 85

    if coverage >= 5:
        return 70

    if coverage >= 3:
        return 50

    if coverage >= 1:
        return 25

    return 0


def _score_debt_to_ebitda(ratio: float | None) -> float:
    """Fallback when interest coverage is unavailable; lower is better."""
    if ratio is None:
        return 0

    if ratio <= 0:
        return 100

    if ratio <= 0.5:
        return 85

    if ratio <= 1.5:
        return 70

    if ratio <= 3.0:
        return 50

    return 25


def analyse_quality(company: Company) -> AnalysisResult:

    roic_score = _score_roic(company.metrics.roic)
    roe_score = _score_roe(company.metrics.roe)
    operating_margin_score = _score_operating_margin(company.metrics.operating_margin)
    revenue_cagr_score = _score_cagr(company.metrics.revenue_cagr)
    eps_cagr_score = _score_cagr(company.metrics.eps_cagr)
    fcf_margin_score = _score_fcf_margin(company.metrics.fcf_margin)
    fcf_conversion_score = _score_fcf_conversion(company.metrics.fcf_conversion)
    net_debt_score = _score_net_debt_ebitda(company.metrics.net_debt_ebitda)
    leverage_score = (
        _score_interest_coverage(company.metrics.interest_coverage)
        if company.metrics.interest_coverage is not None
        else _score_debt_to_ebitda(company.metrics.debt_to_ebitda)
    )

    score = (
        0.25 * roic_score
        + 0.05 * roe_score
        + 0.05 * operating_margin_score
        + 0.10 * revenue_cagr_score
        + 0.15 * eps_cagr_score
        + 0.10 * fcf_margin_score
        + 0.10 * fcf_conversion_score
        + 0.10 * net_debt_score
        + 0.10 * leverage_score
    )

    leverage_label = (
        f"IntCov={num(company.metrics.interest_coverage, 1)}x"
        if company.metrics.interest_coverage is not None
        else f"Debt/EBITDA={num(company.metrics.debt_to_ebitda, 1)}x"
    )
    summary = (
        f"ROIC={pct(company.metrics.roic)} | "
        f"ROE={pct(company.metrics.roe)} | "
        f"Op.Margin={pct(company.metrics.operating_margin)} | "
        f"Rev.CAGR={pct(company.metrics.revenue_cagr)} | "
        f"EPS.CAGR={pct(company.metrics.eps_cagr)} | "
        f"FCF.Margin={pct(company.metrics.fcf_margin)} | "
        f"FCF.Conv={pct(company.metrics.fcf_conversion)} | "
        f"{leverage_label}"
    )

    return AnalysisResult(
        score=round(score, 1),
        summary=summary,
        recommendation=recommendation(score),
    )