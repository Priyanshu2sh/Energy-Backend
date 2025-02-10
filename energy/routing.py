# routing.py
from django.urls import path
from .consumers import NegotiationWindowConsumer
from .test_consumers import TestNegotiationWindowConsumer

websocket_urlpatterns = [
    path('api/energy/ws/negotiation/', NegotiationWindowConsumer.as_asgi()),
    path('api/energy/ws/test-negotiation/', TestNegotiationWindowConsumer.as_asgi()),
]
