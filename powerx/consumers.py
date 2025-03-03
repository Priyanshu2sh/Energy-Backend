import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Notifications

# notifications live counting showing
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope["url_route"]["kwargs"]["user_id"]
        self.group_name = f"user_{self.user_id}"

        # Join the user's notification group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send current unread notification count on connection
        unread_count = await self.get_unread_count()
        await self.send(json.dumps({"unread_count": unread_count}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_notification(self, event):
        """Send new notification update"""
        await self.send(text_data=json.dumps({"unread_count": event["unread_count"]}))

    async def mark_notifications_read(self, event):
        """Clear unread count when user views notifications"""
        await self.send(text_data=json.dumps({"unread_count": 0}))

    @sync_to_async
    def get_unread_count(self):
        return Notifications.objects.filter(user_id=self.user_id, is_read=False).count()