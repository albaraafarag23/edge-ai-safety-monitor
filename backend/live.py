"""In-process fan-out of live events to connected dashboards (Server-Sent Events).

Events are published only after the database commit, so a dashboard that refetches on an
event always finds the new data. One backend instance is assumed; with several, this would
move to Redis pub/sub.
"""
import asyncio
import json


class Broadcaster:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def publish(self, event: str, data: dict):
        message = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        for queue in list(self._subscribers):
            if queue.full():  # a stalled client shouldn't block everyone else
                self._subscribers.discard(queue)
            else:
                queue.put_nowait(message)

    async def stream(self, is_disconnected):
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            yield "retry: 3000\n\n"
            while not await is_disconnected():
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # keeps proxies from closing an idle connection
        finally:
            self._subscribers.discard(queue)


broadcaster = Broadcaster()
