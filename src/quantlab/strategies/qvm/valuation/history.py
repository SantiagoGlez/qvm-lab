class ValuationHistoryService:

    def load(self, ticker: str) -> ValuationHistory:

        pe = self.client.historical_pe(ticker)

        return ValuationHistory(
            ticker=ticker,
            pe_values=pe,
            average=average(pe),
            median=median_value(pe),
            minimum=min(pe),
            maximum=max(pe),
            percentile=percentile(pe, pe[-1]),
            current_pe=pe[-1],
        )