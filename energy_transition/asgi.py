# asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
import energy.routing # Adjust according to your app structure

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'energy_transition.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(
        energy.routing.websocket_urlpatterns        
    )
})

