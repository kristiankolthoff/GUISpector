from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class RunsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        try:
            req_id = self.scope['url_route']['kwargs']['req_id']
        except Exception:
            await self.close()
            return
        self.group_name = f"runs_{req_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # We don't expect inbound messages from clients right now
        pass

    async def run_progress(self, event):
        payload = event.get('payload', {})
        await self.send_json(payload)



class SetupsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # Single shared group for setup-level updates
        self.group_name = "setups"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # No inbound messages expected
        pass

    async def setup_update(self, event):
        payload = event.get('payload', {})
        await self.send_json(payload)
