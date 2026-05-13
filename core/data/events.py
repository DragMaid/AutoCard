from pydantic import BaseModel
from typing import Union


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
    target_id: str


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
]


class EventLogger:
    """Lightweight event logger storing only ID references."""

    def __init__(self):
        self._events: list[GameEvent] = []

    def get_events(self):
        return self._events

    def add_event(self, event: GameEvent):
        self._events.append(event)

    def clear_events(self):
        self._events.clear()
