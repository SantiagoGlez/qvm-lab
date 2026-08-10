from dataclasses import dataclass


@dataclass(slots=True)
class ValuationHistory:

    ticker: str

    pe_values: list[float]

    average: float

    median: float

    minimum: float

    maximum: float

    percentile: float

    current_pe: float