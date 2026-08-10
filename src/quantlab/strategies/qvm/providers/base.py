from abc import ABC, abstractmethod

from ..models import Company


class Provider(ABC):

    @abstractmethod
    def load(self, ticker: str) -> Company:
        """Load a company from the provider."""
        raise NotImplementedError