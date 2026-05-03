from dataclasses import dataclass, asdict
from typing import Union, Any, Type


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

    @staticmethod
    def _get_id(obj: Any) -> str | None:
        """Extract ID from Card or Player object, else return None."""
        if hasattr(obj, "id"):
            return getattr(obj, "id")
        return None

    @classmethod
    def create_attack(cls, card, target):
        return AttackEvent(card_id=cls._get_id(card) or str(card),
                           target_id=cls._get_id(target) or str(target))

    @classmethod
    def create_trap_trigger(cls, card, target):
        return TrapTriggerEvent(card_id=cls._get_id(card) or str(card),
                                target_id=cls._get_id(target) or str(target))

    @classmethod
    def create_toggle(cls, card, mode: str):
        return ToggleEvent(card_id=cls._get_id(card) or str(card), mode=mode)

    @classmethod
    def create_spell_active(cls, spell, target=None, target_type=None):
        return SpellActiveEvent(
            spell_id=cls._get_id(spell) or str(spell),
            target_id=cls._get_id(target) or (str(target) if target else None),
            target_type=target_type
        )

    @classmethod
    def create_merge(cls, card, target, result):
        return MergeEvent(
            card_id=cls._get_id(card) or str(card),
            target_id=cls._get_id(target) or str(target),
            result_card_id=cls._get_id(result) or str(result)
        )

    # TODO: the question is this is only for running the animation
    # One very troublesome thing is that the logic is depleted first but then the UI
    # is updated after instead of immediately removing the sprite
    # Below are built-in functions for network process
    # Then we just have to send an update for every action that happens afterwards
    # The thing is to ask for it to finish running the animation before updating the event list
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
