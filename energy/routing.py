# routing.py
from django.urls import path
from .consumers import NegotiationWindowConsumer

websocket_urlpatterns = [
    path('api/energy/ws/negotiation/', NegotiationWindowConsumer.as_asgi()),
]
