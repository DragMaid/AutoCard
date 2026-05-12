from typing import Dict
from core.factory.base_factory import BaseFactory


class CardRegistry:
    """
    Registry for card factories.
    Factories register themselves here to be accessible globally.
    """
    _factories: Dict[str, BaseFactory] = {}

    @classmethod
    def register(cls, card_type: str, factory: BaseFactory):
        """Register a factory instance."""
        cls._factories[card_type] = factory

    @classmethod
    def get_factory(cls, card_type: str) -> BaseFactory:
        """Retrieve a factory by its type."""
        factory = cls._factories.get(card_type)
        if not factory:
            raise RuntimeError(f"Factory for {card_type} not registered.")
        return factory

    @classmethod
    def create(cls, card_type: str, owner_id: str, name: str | None = None):
        """Create a card instance using the registered factory."""
        return cls.get_factory(card_type).load(owner_id, name)

    @classmethod
    def list_cards(cls, card_type: str) -> dict:
        """List raw cards for a given type."""
        return cls.get_factory(card_type).get_cards()
