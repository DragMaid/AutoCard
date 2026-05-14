from typing import Dict, Optional, Any
from core.factory.base_factory import BaseFactory
from core.cards.card import Card


class CardRegistry:
    """Registry for card factories.

    Factories register themselves here to be accessible globally.
    """
    _factories: Dict[str, BaseFactory] = {}

    @classmethod
    def register(cls, card_type: str, factory: BaseFactory) -> None:
        """Registers a factory instance.

        Args:
            card_type (str): The type of card the factory handles.
            factory (BaseFactory): The factory instance to register.
        """
        cls._factories[card_type] = factory

    @classmethod
    def get_factory(cls, card_type: str) -> BaseFactory:
        """Retrieves a factory by its type.

        Args:
            card_type (str): The type of card to get the factory for.

        Returns:
            BaseFactory: The requested factory.

        Raises:
            RuntimeError: If the factory is not registered.
        """
        factory = cls._factories.get(card_type)
        if not factory:
            raise RuntimeError(f"Factory for {card_type} not registered.")
        return factory

    @classmethod
    def create(cls, card_type: str, owner_id: str, name: Optional[str] = None) -> Card:
        """Creates a card instance using the registered factory.

        Args:
            card_type (str): The type of card to create.
            owner_id (str): The ID of the owner.
            name (Optional[str]): The name of the card.

        Returns:
            Card: A new card instance.
        """
        return cls.get_factory(card_type).load(owner_id, name)

    @classmethod
    def list_cards(cls, card_type: str) -> Dict[str, Dict[str, Any]]:
        """Lists raw cards for a given type.

        Args:
            card_type (str): The type of card.

        Returns:
            Dict[str, Dict[str, Any]]: A dictionary of card data.
        """
        return cls.get_factory(card_type).get_cards()
