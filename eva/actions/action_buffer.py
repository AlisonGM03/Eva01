"""
ActionBuffer: Outgoing event bus for EVA's actions.

Tools push events:       await buffer.put("speak", text)
Consumers register:      buffer.on("speak", handler)
Spine runs the loop:     await buffer.start_loop()
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
import time
from typing import Callable, Awaitable, Optional

from config import logger


@dataclass
class ActionEvent:
    """A single action command."""
    type: str
    content: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# Handler signature: async def handler(event: ActionEvent) -> None
ActionHandler = Callable[[ActionEvent], Awaitable[None]]


class ActionBuffer:
    """
    Async event bus — tools push, registered handlers consume.
    """

    def __init__(self):
        self._queue: asyncio.Queue[ActionEvent] = asyncio.Queue()
        self._handlers: dict[str, list[ActionHandler]] = defaultdict(list)
        self._running = False

    def on(self, action_type: str, handler: ActionHandler) -> None:
        """Register a handler for an action type."""
        self._handlers[action_type].append(handler)
        logger.debug(f"ActionBuffer: registered handler for <{action_type}>")

    async def put(
        self,
        action_type: str,
        content: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Push an action command."""
        event = ActionEvent(
            type=action_type,
            content=content,
            metadata=metadata or {},
        )
        await self._queue.put(event)
        logger.debug(f"ActionBuffer: put <{action_type}> — {len(str(content).split())} words.")

    async def start_loop(self) -> None:
        """Dispatch events to registered handlers. Runs forever."""
        self._running = True
        logger.debug("ActionBuffer: dispatch loop started.")

        while self._running:
            try:
                event = await self._queue.get()
                handlers = self._handlers.get(event.type)

                if not handlers:
                    logger.warning(f"ActionBuffer: no handler for <{event.type}>, dropped.")
                    continue

                for handler in handlers:
                    try:
                        await handler(event)
                    except Exception as e:
                        logger.error(f"ActionBuffer: handler error for <{event.type}> — {e}")

            except asyncio.CancelledError:
                logger.debug("ActionBuffer: dispatch loop cancelled.")
                self._running = False
                break

    async def stop(self) -> None:
        """Stop the dispatch loop."""
        self._running = False

    def empty(self) -> bool:
        """Check if the buffer is empty."""
        return self._queue.empty()
