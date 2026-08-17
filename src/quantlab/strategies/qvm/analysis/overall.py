from ..models import Company


def overall_score(company: Company) -> float:

    analyses = [
        company.valuation.score,
        company.quality.score,
    ]

    analyses = [score for score in analyses if score > 0]

    if not analyses:
        return 0

    return round(sum(analyses) / len(analyses), 1)


def report_overall_score(company: Company) -> float:
    """Report-facing overall score.

    For now, reports are quality-led and valuation is informative only.
    Keep this separate from `overall_score` so backtest/scoring logic can evolve independently.
    """
    return round(company.quality.score, 1)