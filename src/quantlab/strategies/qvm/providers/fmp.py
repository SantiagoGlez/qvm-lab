from __future__ import annotations

import httpx


class FmpClient:
    """
    Thin wrapper around the Financial Modeling Prep API.

    This class should ONLY be responsible for making HTTP requests.
    It should not contain any business logic.
    """

    BASE_URL = "https://financialmodelingprep.com/stable"

    def __init__(self, api_key: str):

        self.api_key = api_key

        self.client = httpx.Client(
            timeout=20,
            follow_redirects=True,
        )

    def _get(self, endpoint: str, params: dict | None = None):

        response = self.client.get(
            f"{self.BASE_URL}/{endpoint}",
            params={
                "apikey": self.api_key,
                **(params or {}),
            },
        )

        response.raise_for_status()

        return response.json()

    def company_profile(self, ticker: str):

        return self._get("profile", params={"symbol": ticker})

    def key_metrics(self, ticker: str):

        return self._get("key-metrics", params={"symbol": ticker})

    def ratios(self, ticker: str):

        return self._get("ratios", params={"symbol": ticker})

    def income_statement(self, ticker: str):

        return self._get("income-statement", params={"symbol": ticker})

    def close(self):

        self.client.close()