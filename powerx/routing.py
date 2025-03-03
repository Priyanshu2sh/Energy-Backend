# routing.py
from django.urls import path
from .consumers import NotificationConsumer

websocket_urlpatterns = [
    path("api/powerx/notifications/<int:user_id>/", NotificationConsumer.as_asgi()),
]
