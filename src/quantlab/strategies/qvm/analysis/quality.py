from ..models import AnalysisResult, Company


_QUALITY_WEIGHTS = {
    "roic": 0.25,
    "roe": 0.05,
    "operating_margin": 0.05,
    "revenue_cagr": 0.10,
    "eps_cagr": 0.15,
    "fcf_margin": 0.10,
    "fcf_conversion": 0.10,
    "net_debt_ebitda": 0.10,
    "leverage": 0.10,
}


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


_QUALITY_METRIC_LABELS = {
    "roic": "ROIC",
    "roe": "ROE",
    "operating_margin": "Operating Margin",
    "revenue_cagr": "Revenue CAGR",
    "eps_cagr": "EPS CAGR",
    "fcf_margin": "FCF Margin",
    "fcf_conversion": "FCF Conversion",
    "net_debt_ebitda": "Net Debt/EBITDA",
    "leverage": "Leverage",
}


def quality_missing_metrics(company: Company) -> list[str]:
    """Return human-readable names for quality metrics missing from the company snapshot."""
    metric_values = {
        "roic": company.metrics.roic,
        "roe": company.metrics.roe,
        "operating_margin": company.metrics.operating_margin,
        "revenue_cagr": company.metrics.revenue_cagr,
        "eps_cagr": company.metrics.eps_cagr,
        "fcf_margin": company.metrics.fcf_margin,
        "fcf_conversion": company.metrics.fcf_conversion,
        "net_debt_ebitda": company.metrics.net_debt_ebitda,
        "leverage": (
            company.metrics.interest_coverage
            if company.metrics.interest_coverage is not None
            else company.metrics.debt_to_ebitda
        ),
    }

    return [
        _QUALITY_METRIC_LABELS[name]
        for name, value in metric_values.items()
        if value is None
    ]


def quality_metric_coverage(company: Company) -> float:
    """Fraction of the quality dimensions that are populated."""
    metric_values = [
        company.metrics.roic,
        company.metrics.roe,
        company.metrics.operating_margin,
        company.metrics.revenue_cagr,
        company.metrics.eps_cagr,
        company.metrics.fcf_margin,
        company.metrics.fcf_conversion,
        company.metrics.net_debt_ebitda,
        company.metrics.interest_coverage if company.metrics.interest_coverage is not None else company.metrics.debt_to_ebitda,
    ]
    available = sum(1 for value in metric_values if value is not None)
    return available / len(metric_values) if metric_values else 0.0


def quality_eligible(company: Company, minimum_coverage: float = 0.7) -> bool:
    """Return whether the company clears the minimum quality coverage gate."""
    return quality_metric_coverage(company) >= minimum_coverage


def quality_snapshot(company: Company) -> dict[str, float | bool | str | list[str]]:
    """Return coverage metadata for external snapshot/export consumers without changing scoring."""
    quality_result = analyse_quality(company)
    return {
        "quality_score": quality_result.score,
        "quality_coverage": quality_result.coverage,
        "quality_eligible": quality_result.eligible,
        "missing_metrics": ", ".join(quality_result.missing_metrics) if quality_result.missing_metrics else "",
    }


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

    metric_scores = {
        "roic": (company.metrics.roic, roic_score),
        "roe": (company.metrics.roe, roe_score),
        "operating_margin": (company.metrics.operating_margin, operating_margin_score),
        "revenue_cagr": (company.metrics.revenue_cagr, revenue_cagr_score),
        "eps_cagr": (company.metrics.eps_cagr, eps_cagr_score),
        "fcf_margin": (company.metrics.fcf_margin, fcf_margin_score),
        "fcf_conversion": (company.metrics.fcf_conversion, fcf_conversion_score),
        "net_debt_ebitda": (company.metrics.net_debt_ebitda, net_debt_score),
        "leverage": (
            company.metrics.interest_coverage if company.metrics.interest_coverage is not None else company.metrics.debt_to_ebitda,
            leverage_score,
        ),
    }

    coverage = quality_metric_coverage(company)
    missing_metrics = quality_missing_metrics(company)
    weighted_total = 0.0
    available_weight = 0.0
    for metric_name, (value, score_value) in metric_scores.items():
        if value is None:
            continue
        available_weight += _QUALITY_WEIGHTS[metric_name]
        weighted_total += _QUALITY_WEIGHTS[metric_name] * score_value

    score = (weighted_total / available_weight) if available_weight > 0 else 0.0

    leverage_label = (
        f"IntCov={num(company.metrics.interest_coverage, 1)}x"
        if company.metrics.interest_coverage is not None
        else f"Debt/EBITDA={num(company.metrics.debt_to_ebitda, 1)}x"
    )
    summary = (
        f"Coverage={coverage:.0%} | "
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
        coverage=coverage,
        missing_metrics=missing_metrics,
        eligible=quality_eligible(company),
    )