from typing import Tuple, Optional, Dict, Any


class ActionCodec:
    """
    Handles encoding and decoding of game actions into a fixed discrete action space.

    Action ID Ranges:
    - 0: End Turn
    - 1-10: Summon (Hand Slot 0-9)
    - 11-20: Set Trap (Hand Slot 0-9)
    - 21-230: Cast Spell (Hand Slot 0-9 x Target 0-20)
        Target 0: None
        Target 1-10: Own Field Slots 0-9
        Target 11-20: Opponent Field Slots 0-9
    - 231-340: Attack (Attacker Slot 0-9 x Target 0-10)
        Target 0-9: Opponent Field Slots 0-9
        Target 10: Opponent Player Direct
    - 341-350: Toggle (Slot 0-9)
    - 351-450: Combine (Slot A 0-9 x Slot B 0-9)
    - 451-460: Activate Trap (Slot 0-9)
    """

    NUM_ACTIONS = 461

    @staticmethod
    def decode(action_id: int) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Decode a discrete action ID into a (name, params) tuple."""
        if action_id == 0:
            return "end_turn", {}

        # Summon: 1-10
        if 1 <= action_id <= 10:
            return "summon", {"monster": action_id - 1}

        # Set Trap: 11-20
        if 11 <= action_id <= 20:
            return "set_trap", {"trap": action_id - 11}

        # Cast Spell: 21-230
        if 21 <= action_id <= 230:
            offset = action_id - 21
            hand_idx = offset // 21
            target_idx = offset % 21

            # Map target_idx back to what the handler expects
            # Handler expects: target_id or None
            # Here we just pass the index, the environment will map it to ID
            return "cast_spell", {"spell": hand_idx, "target": target_idx}

        # Attack: 231-340
        if 231 <= action_id <= 340:
            offset = action_id - 231
            attacker_slot = offset // 11
            target_slot = offset % 11
            return "attack", {"attacker": attacker_slot, "target": target_slot}

        # Toggle: 341-350
        if 341 <= action_id <= 350:
            return "toggle", {"toggle": action_id - 341}

        # Combine: 351-450
        if 351 <= action_id <= 450:
            offset = action_id - 351
            slot_a = offset // 10
            slot_b = offset % 10
            return "combine", {"pair": (slot_a, slot_b)}

        # Activate Trap: 451-460
        if 451 <= action_id <= 460:
            return "activate_trap", {"trap": action_id - 451}

        return "end_turn", {}

    @staticmethod
    def encode_summon(hand_idx: int) -> int:
        return 1 + hand_idx

    @staticmethod
    def encode_set_trap(hand_idx: int) -> int:
        return 11 + hand_idx

    @staticmethod
    def encode_cast_spell(hand_idx: int, target_idx: int) -> int:
        return 21 + (hand_idx * 21) + target_idx

    @staticmethod
    def encode_attack(attacker_slot: int, target_slot: int) -> int:
        return 231 + (attacker_slot * 11) + target_slot

    @staticmethod
    def encode_toggle(slot_idx: int) -> int:
        return 341 + slot_idx

    @staticmethod
    def encode_combine(slot_a: int, slot_b: int) -> int:
        return 351 + (slot_a * 10) + slot_b

    @staticmethod
    def encode_activate_trap(slot_idx: int) -> int:
        return 451 + slot_idx
