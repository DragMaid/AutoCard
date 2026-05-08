import logging
def draw_specific_card(engine, player_id: str, name: str, ctype: str):
    if ctype == "monster":
        card = engine.monster_factory.load(player_id, name)
    elif ctype == "trap":
        card = engine.trap_factory.load(player_id, name)
    elif ctype == "spell":
        card = engine.spell_factory.load(player_id, name)
    else:
        return
    engine.game_state.entity_lookup[card.id] = card
    engine.game_state.player_info[player_id]["held_cards"].add(card.id)
    print(f"[DEBUG] {player_id} received specific card: {name}")


def log_action(action_type: str, player_id: str, details: dict, success: bool):
    """Central logging method for all game actions"""
    status = "SUCCESS" if success else "FAILED"
    log_msg = f"[Action [{status}] {action_type} by {player_id}"
    logger = logging.getLogger("GameEngine")

    # Add relevant details
    detail_parts = []
    for key, value in details.items():
        detail_parts.append(f"{key}={value}")

    if detail_parts:
        log_msg += f" | {', '.join(detail_parts)}"

    logger.info(log_msg) if success else logger.error(log_msg)
