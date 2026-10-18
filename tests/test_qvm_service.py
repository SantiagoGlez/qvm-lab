from quantlab.strategies.qvm.service import _recompute_percentile


def test_recompute_percentile_matches_provider_style_for_live_pe() -> None:
    historical_pe_values = [12.9, 17.0, 67.7]

    percentile = _recompute_percentile(historical_pe_values, 15.13)

    assert percentile == 1 / 3