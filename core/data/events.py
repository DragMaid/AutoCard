from dataclasses import dataclass, asdict
from typing import Union, Type


@dataclass
class AttackEvent:
    card_id: str
    target_id: str
    target_is_player: bool


@dataclass
class TrapTriggerEvent:
    card_id: str
    target_id: str


@dataclass
class TrapTriggerableEvent:
    card_id: str


@dataclass
class ToggleEvent:
    card_id: str
    mode: str


@dataclass
class SpellActiveEvent:
    spell_id: str
    target_id: str


@dataclass
class MergeEvent:
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

    # Basic accessors
    def get_events(self):
        return self._events

    def add_event(self, event: GameEvent):
        self._events.append(event)

    def clear_events(self):
        self._events.clear()

    def serialize(self):
        """Convert EventLogger contents into a serializable dict."""
        return {
            "events": [
                {"type": e.__class__.__name__, "data": asdict(e)}
                for e in self._events
            ]
        }

    def deserialize(self, serialized):
        """Rebuild EventLogger from serialized dict (ID-only)."""
        event_map: dict[str, Type[GameEvent]] = {
            "AttackEvent": AttackEvent,
            "TrapTriggerEvent": TrapTriggerEvent,
            "TrapTriggerableEvent": TrapTriggerableEvent,
            "ToggleEvent": ToggleEvent,
            "SpellActiveEvent": SpellActiveEvent,
            "MergeEvent": MergeEvent,
        }

        events = []
        for ev in serialized.get("events", []):
            ev_type = ev.get("type")
            ev_data = ev.get("data", {})
            cls = event_map.get(ev_type)
            if not cls:
                continue
            try:
                event = cls(**ev_data)
                events.append(event)
            except TypeError:
                # Skip malformed entries
                continue

        self._events = events
