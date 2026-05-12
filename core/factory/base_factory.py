from abc import ABC, abstractmethod


class BaseFactory(ABC):
    @abstractmethod
    def build(self):
        """Load card data from source."""
        raise NotImplementedError

    @abstractmethod
    def load(self, owner_id: str, name: str | None = None):
        """Create a card instance."""
        raise NotImplementedError

    @abstractmethod
    def get_cards(self) -> dict:
        """Return raw card data."""
        raise NotImplementedError
