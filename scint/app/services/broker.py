import asyncio
from collections import deque

import redis.asyncio as redis
from falcon.asgi import Request, WebSocket
from falcon.errors import WebSocketDisconnected

from scint.framework.entities.service import Service


class Broker(Service):
    def __init__(self, context, url):
        super().__init__()
        self.url = url
        self.messages = deque()

    async def publish(self, obj):
        r = await redis.from_url(self.url)
        await self.subscribe()
        await r.publish("input", obj)

    async def subscribe(self):
        r = await redis.from_url(self.url)
        async with r.pubsub() as pubsub:
            if not pubsub.subscribed:
                await pubsub.subscribe("output")
            await asyncio.create_task(self._reader(pubsub))

    async def _reader(self, pubsub):
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message is not None:
                self.messages.append(message["data"].decode())

    async def on_websocket(self, req: Request, ws: WebSocket):
        try:
            await ws.accept()
            await self.process_websocket(req, ws)
        except WebSocketDisconnected:
            await ws.close()

    async def process_websocket(self, req: Request, ws: WebSocket):
        async def sink():
            while True:
                try:
                    message = await ws.receive_text()
                    await self.publish(message)
                except WebSocketDisconnected:
                    break

        sink_task = asyncio.create_task(sink())

        while not sink_task.done():
            while ws.ready and not self.messages and not sink_task.done():
                await asyncio.sleep(0.1)
            try:
                await ws.send_text(self.messages.popleft())
            except WebSocketDisconnected:
                break

        sink_task.cancel()

        try:
            await sink_task
        except asyncio.CancelledError:
            pass