"""Transport that hands engine patches to the room's outbound queue."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from core.network.actions import Patch

logger = logging.getLogger(__name__)


class AsyncQueueTransport:
    """Pushes patches from engine code onto an asyncio queue.

    ``GameEngine`` calls :meth:`send_patch` synchronously from inside its
    transaction, which may be running either on the event loop or on a worker
    thread (AI inference is offloaded so torch cannot stall the loop). Hopping
    through ``call_soon_threadsafe`` is correct in both cases and preserves the
    order patches were produced in.

    A patch is split into one envelope per addressee before it is queued, which
    is what keeps a player's hand out of the other player's socket. Splitting
    happens here, synchronously, rather than in the pump: it reads the engine to
    work out what each seat may see, and by the time the pump runs the engine has
    moved on.

    Attributes:
        queue: Queue drained by the room's outbound pump.
        loop: The loop that owns :attr:`queue`.
    """

    def __init__(self, queue: "asyncio.Queue[dict[str, Any]]",
                 loop: asyncio.AbstractEventLoop,
                 fanout: Optional[Callable[[Patch], list[dict[str, Any]]]] = None,
                 ) -> None:
        """Initializes the transport.

        Args:
            queue: Queue the room pumps onto its relay socket.
            loop: Event loop owning the queue.
            fanout: Splits one patch into per-addressee envelopes. Without it the
                patch is queued once, unredacted, for everyone in the room.
        """
        self.queue = queue
        self.loop = loop
        self.fanout = fanout

    def send_patch(self, patch: Patch) -> None:
        """Queues one patch for the room's addressees.

        Args:
            patch (Patch): The delta the engine just produced.
        """
        try:
            envelopes = (self.fanout(patch) if self.fanout is not None
                         else [{"player_id": None, "patch": patch.model_dump(mode="json")}])
        except Exception:
            # Never let a redaction failure escape into the rules: the engine is
            # mid-transaction here, and the alternative to dropping the patch is
            # sending an unfiltered one.
            logger.exception("Could not prepare patch %s for sending", patch.seq)
            return

        for envelope in envelopes:
            try:
                self.loop.call_soon_threadsafe(self.queue.put_nowait, envelope)
            except RuntimeError:
                # The loop closed while a room was tearing down.
                logger.debug("Dropped patch %s: loop is gone", patch.seq)
                return
