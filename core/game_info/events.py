from dataclasses import dataclass, asdict
from typing import Union, Any, Type


# -------------------------------------------------
# EVENT DEFINITIONS (ID-ONLY)
# -------------------------------------------------
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


# -------------------------------------------------
# EVENT LOGGER
# -------------------------------------------------
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

    # -------------------------------------------------
    # FACTORY HELPERS
    # -------------------------------------------------
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

    # -------------------------------------------------
    # SERIALIZATION
    # -------------------------------------------------
    @staticmethod
    def _serialize_events(event_logger: "EventLogger") -> dict:
        """Convert EventLogger contents into a serializable dict."""
        return {
            "events": [
                {"type": e.__class__.__name__, "data": asdict(e)}
                for e in event_logger._events
            ]
        }

    # -------------------------------------------------
    # DESERIALIZATION
    # -------------------------------------------------
    @staticmethod
    def _deserialize_events(serialized: dict) -> "EventLogger":
        """Rebuild EventLogger from serialized dict (ID-only)."""
        event_map: dict[str, Type[GameEvent]] = {
            "AttackEvent": AttackEvent,
            "TrapTriggerEvent": TrapTriggerEvent,
            "ToggleEvent": ToggleEvent,
            "SpellActiveEvent": SpellActiveEvent,
            "MergeEvent": MergeEvent,
        }

        logger = EventLogger()

        for ev in serialized.get("events", []):
            ev_type = ev.get("type")
            ev_data = ev.get("data", {})
            cls = event_map.get(ev_type)
            if not cls:
                continue
            try:
                event = cls(**ev_data)
                logger.add_event(event)
            except TypeError:
                # Skip malformed entries
                continue

        return logger
