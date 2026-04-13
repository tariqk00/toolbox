"""Abstract base for inbox scanner category processors."""
from abc import ABC, abstractmethod


class CategoryProcessor(ABC):
    @abstractmethod
    def category_name(self) -> str:
        pass

    @abstractmethod
    def process(self, email: dict, classification: dict) -> dict | None:
        """Process an email and return a result dict, or None to skip."""
        pass
