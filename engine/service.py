"""WebSocket service fronting one authoritative engine per room.

The C# relay opens one socket per room, at ``/<room_id>?mode=pvp|ai``, and speaks
a four-message envelope protocol:

======================  =========  ====================================
``type``                Direction  Meaning
======================  =========  ====================================
``room_ready``          out        Seats and player ids for this room
``patch``               out        A delta to broadcast to both clients
``rejected``            out        An intent broke a rule; nothing changed
``intent``              in         Apply this intent
``dispose``             in         Discard this room's state
======================  =========  ====================================

Coordinates are never transformed here or in the relay. Everything on the wire is
in the host's canonical frame and each client mirrors from its own seat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from aiohttp import WSMsgType, web

from engine.config import EngineConfig
from engine.room import MODE_AI, MODE_PVP, Room

logger = logging.getLogger(__name__)

#: Room ids are used as routing keys, so restrict them to what the relay sends.
_ROOM_ID = re.compile(r"^[A-Za-z0-9_-]{1,24}$")


class EngineService:
    """Owns every live room and the socket serving each one.

    Attributes:
        rooms: Live rooms by id.
        config: Runtime settings.
    """

    def __init__(self, config: type[EngineConfig] = EngineConfig) -> None:
        """Initializes an empty service.

        Args:
            config: Engine settings, overridable in tests.
        """
        self.rooms: dict[str, Room] = {}
        self.config = config

    # ------------------------------------------------------------------
    # Room lifecycle
    # ------------------------------------------------------------------

    def get_or_create(self, room_id: str, mode: str) -> Room:
        """Returns a room, building it if this is the first connection.

        Args:
            room_id (str): Validated room identifier.
            mode (str): ``pvp`` or ``ai``; ignored for an existing room.

        Returns:
            Room: The live room.
        """
        room = self.rooms.get(room_id)
        if room is not None and not room.closed:
            return room

        room = Room(room_id, mode, asyncio.get_running_loop(), self.config)
        self.rooms[room_id] = room
        logger.info("Created room %s in %s mode", room_id, room.mode)
        return room

    async def discard(self, room_id: str) -> None:
        """Closes and forgets a room.

        Args:
            room_id (str): Room to drop.
        """
        room = self.rooms.pop(room_id, None)
        if room is not None:
            await room.close()

    async def sweep(self) -> None:
        """Closes rooms whose relay has been gone past the TTL."""
        for room_id, room in list(self.rooms.items()):
            if room.is_expired:
                logger.info("Expiring idle room %s", room_id)
                await self.discard(room_id)

    async def sweep_forever(self, interval: float = 30.0) -> None:
        """Runs :meth:`sweep` on a timer for the life of the process.

        Args:
            interval (float): Seconds between sweeps.
        """
        while True:
            await asyncio.sleep(interval)
            try:
                await self.sweep()
            except Exception:
                logger.exception("Room sweep failed")

    # ------------------------------------------------------------------
    # HTTP surface
    # ------------------------------------------------------------------

    async def handle(self, request: web.Request) -> web.StreamResponse:
        """Serves one relay connection for the lifetime of its socket.

        Args:
            request: The upgrade request; its path names the room.

        Returns:
            The WebSocket response.
        """
        room_id = request.match_info.get("room_id", "").strip()
        if not _ROOM_ID.match(room_id):
            raise web.HTTPBadRequest(text="Invalid room id")

        requested = request.query.get("mode", MODE_PVP)
        mode = MODE_AI if requested == MODE_AI else MODE_PVP

        socket = web.WebSocketResponse(heartbeat=30.0, max_msg_size=256 * 1024)
        await socket.prepare(request)

        room = self.get_or_create(room_id, mode)
        room.attach(socket)
        await socket.send_json(room.describe())
        logger.info("Relay attached to room %s", room_id)

        try:
            await self._read(room, socket)
        finally:
            room.detach(socket)
            logger.info("Relay detached from room %s", room_id)

        return socket

    async def _read(self, room: Room, socket: web.WebSocketResponse) -> None:
        """Feeds relay messages into the room until the socket closes.

        Args:
            room (Room): The room this socket serves.
            socket: The relay socket.
        """
        async for message in socket:
            if message.type is not WSMsgType.TEXT:
                continue

            try:
                envelope: Any = json.loads(message.data)
            except json.JSONDecodeError:
                logger.warning("Room %s got unparseable relay data", room.room_id)
                continue

            if not isinstance(envelope, dict):
                continue

            if envelope.get("type") == "dispose":
                await self.discard(room.room_id)
                await socket.close()
                return

            room.submit(envelope)

    async def health(self, request: web.Request) -> web.Response:
        """Reports liveness and room count.

        Args:
            request: The HTTP request.

        Returns:
            A small JSON body.
        """
        return web.json_response({
            "status": "ok",
            "rooms": len(self.rooms),
            "checkpoint": str(self.config.CHECKPOINT_PATH),
            "checkpoint_present": self.config.CHECKPOINT_PATH.exists(),
        })


def build_app(config: type[EngineConfig] = EngineConfig) -> web.Application:
    """Builds the aiohttp application.

    Args:
        config: Engine settings, overridable in tests.

    Returns:
        web.Application: The configured app.
    """
    service = EngineService(config)
    app = web.Application()
    app["service"] = service
    app.router.add_get("/health", service.health)
    app.router.add_get("/{room_id}", service.handle)

    async def _start_sweeper(app: web.Application) -> None:
        app["sweeper"] = asyncio.create_task(service.sweep_forever())

    async def _stop(app: web.Application) -> None:
        app["sweeper"].cancel()
        for room_id in list(service.rooms):
            await service.discard(room_id)

    app.on_startup.append(_start_sweeper)
    app.on_cleanup.append(_stop)
    return app


def main() -> None:
    """Runs the engine service until interrupted."""
    app = build_app()
    logger.info("Engine service listening on %s:%s",
                EngineConfig.HOST, EngineConfig.PORT)
    web.run_app(app, host=EngineConfig.HOST, port=EngineConfig.PORT,
                print=None)
