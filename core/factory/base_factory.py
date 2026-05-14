from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseFactory(ABC):
    @abstractmethod
    def build(self) -> None:
        """Loads card data from source."""
        raise NotImplementedError

    @abstractmethod
    def load(self, owner_id: str, name: Optional[str] = None) -> Any:
        """Creates a card instance.

        Args:
            owner_id (str): The ID of the owner.
            name (Optional[str]): The name of the card to create.

        Returns:
            Any: A card instance.
        """
        raise NotImplementedError

    @abstractmethod
    def get_cards(self) -> Dict[str, Any]:
        """Returns raw card data.

        Returns:
            Dict[str, Any]: A dictionary of card data.
        """
        raise NotImplementedError
