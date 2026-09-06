"""Transports that carry intents and patches between engines.

A transport is any object with ``send_intent`` and/or ``send_patch``. The
authoritative engine only ever calls ``send_patch``; a remote client engine only
ever calls ``send_intent``.
"""

from __future__ import annotations

import logging
from typing import Any

from core.network.actions import Intent, Patch

logger = logging.getLogger(__name__)

# Socket.IO event names shared by the pygame client, the relay and the frontend.
EVENT_INTENT = "action"
EVENT_PATCH = "patch"
EVENT_ASSIGN = "assign"


class QueueTransport:
    """Publishes patches onto a multiprocessing queue.

    The pygame host runs its socket server in a separate process, so the
    authoritative engine hands patches to that process through a queue rather
    than emitting them directly.

    Attributes:
        out_queue: Queue drained by the socket server process.
    """

    def __init__(self, out_queue: Any) -> None:
        """Initializes the transport.

        Args:
            out_queue: A queue accepting ``(event_name, payload)`` tuples.
        """
        self.out_queue = out_queue

    def send_patch(self, patch: Patch) -> None:
        """Queues a patch for broadcast to the room.

        Args:
            patch (Patch): The delta to broadcast.
        """
        self.out_queue.put((EVENT_PATCH, patch.model_dump(mode="json")))

    def send_assignment(self, payload: dict) -> None:
        """Queues a seat assignment for a joining client.

        Args:
            payload (dict): Room and player identity for the client.
        """
        self.out_queue.put((EVENT_ASSIGN, payload))


class SocketIntentTransport:
    """Sends intents to the authoritative engine over a Socket.IO client.

    Attributes:
        sio: A connected ``socketio.Client``.
    """

    def __init__(self, sio: Any) -> None:
        """Initializes the transport.

        Args:
            sio: The Socket.IO client used to reach the server or relay.
        """
        self.sio = sio

    def send_intent(self, intent: Intent) -> None:
        """Emits an intent to the server.

        Args:
            intent (Intent): The ID-only action request.
        """
        if not getattr(self.sio, "connected", False):
            logger.warning("Dropping intent %s: socket not connected",
                           intent.type)
            return
        self.sio.emit(EVENT_INTENT, intent.model_dump(mode="json"))
