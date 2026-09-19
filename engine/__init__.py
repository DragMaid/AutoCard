"""Authoritative engine service for networked and single-player AutoCard.

One :class:`~core.logic.game_engine.GameEngine` per room, wrapped in a WebSocket
server the C# relay connects to. The relay owns rooms, seats and fan-out; this
package owns every rule and every random outcome.
"""
