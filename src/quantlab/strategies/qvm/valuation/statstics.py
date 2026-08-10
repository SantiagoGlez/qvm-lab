from statistics import mean, median


def average(values: list[float]) -> float:
    return mean(values)


def median_value(values: list[float]) -> float:
    return median(values)


def percentile(values: list[float], current: float) -> float:

    lower = sum(v <= current for v in values)

    return 100 * lower / len(values)