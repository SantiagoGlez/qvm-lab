from ..models import Company

from .quality import analyse_quality
from .valuation import analyse_valuation


def calculate_score(company: Company) -> None:

    company.valuation = analyse_valuation(company)

    company.quality = analyse_quality(company)