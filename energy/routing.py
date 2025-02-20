# routing.py
from django.urls import path
from .consumers import NegotiationWindowConsumer
from .test_consumers import TestNegotiationWindowConsumer, NotificationConsumer, TermsSheetConsumer, CountsConsumer

websocket_urlpatterns = [
    path('api/energy/ws/negotiation/', NegotiationWindowConsumer.as_asgi()),
    path('api/energy/ws/test-negotiation/', TestNegotiationWindowConsumer.as_asgi()),
    path("api/notifications/<int:user_id>/", NotificationConsumer.as_asgi()),
    path("api/terms-sheet/<int:user_id>", TermsSheetConsumer.as_asgi()),
    path("api/counts/<int:user_id>", CountsConsumer.as_asgi()),
]
