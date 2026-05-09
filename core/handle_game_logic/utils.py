import logging


def draw_specific_card(engine, player_id: str, name: str, ctype: str):
    if ctype == "monster":
        card = engine.draw_syste.monster_factory.load(player_id, name)
    elif ctype == "trap":
        card = engine.draw_system.trap_factory.load(player_id, name)
    elif ctype == "spell":
        card = engine.draw_system.spell_factory.load(player_id, name)
    else:
        return
    engine.game_state.entity_lookup[card.id] = card
    engine.game_state.player_info[player_id]["held_cards"].add(card.id)
    print(f"[DEBUG] {player_id} received specific card: {name}")


def log_action(action_type: str, player_id: str, details: dict, success: bool):
    """Central logging method for all game actions"""
    status = "SUCCESS" if success else "FAILED"
    log_msg = f"[Action [{status}] {action_type} by {player_id}"
    # TODO: should have a centrailize logging getter method
    logger = logging.getLogger("GameEngine")

    # Add relevant details
    detail_parts = []
    for key, value in details.items():
        detail_parts.append(f"{key}={value}")

    if detail_parts:
        log_msg += f" | {', '.join(detail_parts)}"

    logger.info(log_msg) if success else logger.error(log_msg)


def is_local_turn(turn_manager, players) -> bool:
    # TODO: should I move this elsewhere
    trapper = turn_manager.get_trapper()
    current = turn_manager.get_current_player()
    for p in players:
        if not p.is_opponent:
            local = p
            break

    if trapper:
        return trapper.id == local.id

    return current.id == local.id
