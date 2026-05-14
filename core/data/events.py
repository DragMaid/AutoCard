from pydantic import BaseModel
from typing import Union, List, Optional
from pydantic import TypeAdapter


class AttackEvent(BaseModel):
    card_id: str
    target_id: str
    target_is_player: bool


class TrapTriggerEvent(BaseModel):
    card_id: str
    target_id: str


class TrapTriggerableEvent(BaseModel):
    card_id: str


class ToggleEvent(BaseModel):
    card_id: str
    mode: str


class SpellActiveEvent(BaseModel):
    spell_id: str
    target_id: Optional[str]


class MergeEvent(BaseModel):
    card_id: str
    target_id: str
    result_card_id: str


GameEvent = Union[
    AttackEvent,
    TrapTriggerEvent,
    ToggleEvent,
    SpellActiveEvent,
    MergeEvent,
    TrapTriggerableEvent
]

GameEventAdapter = TypeAdapter(GameEvent)


class EventLogger:
    """Lightweight event logger storing only ID references."""

    def __init__(self) -> None:
        self._events: List[GameEvent] = []

    def serialize(self) -> List[dict]:
        """Serializes events to a list of dictionaries.

        Returns:
            A list of serialized event data.
        """
        return [e.model_dump() for e in self._events]

    def deserialize(self, serialized: List[dict]) -> None:
        """Deserializes event data and populates the logger.

        Args:
            serialized: A list of serialized event data.
        """
        self._events = [GameEventAdapter.validate_python(
            e) for e in serialized]

    def get_events(self) -> List[GameEvent]:
        """Returns the list of stored events.

        Returns:
            A list of GameEvent objects.
        """
        return self._events

    def add_event(self, event: GameEvent) -> None:
        """Adds an event to the logger.

        Args:
            event: The game event to be added.
        """
        self._events.append(event)

    def clear_events(self) -> None:
        """Clears all events from the logger."""
        self._events.clear()
