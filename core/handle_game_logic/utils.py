# DEBUG FUNCTION
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
