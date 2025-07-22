# asgi.py
import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'energy_transition.settings')

# 🟢 Must be done before importing anything that touches models
django.setup()

import energy.routing  # These may import consumers/models
import powerx.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(
        energy.routing.websocket_urlpatterns + powerx.routing.websocket_urlpatterns 
    )
})
