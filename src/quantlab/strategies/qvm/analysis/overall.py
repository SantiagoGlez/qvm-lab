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