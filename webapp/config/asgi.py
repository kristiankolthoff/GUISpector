"""
ASGI config for gui_rerank_webapp project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from django.urls import re_path

# Temporary compatibility shim for certain Channels builds expecting DEFAULT_CHANNEL_LAYER
try:
    import channels as _channels
    if not hasattr(_channels, "DEFAULT_CHANNEL_LAYER"):
        _channels.DEFAULT_CHANNEL_LAYER = "default"
except Exception:
    pass

from setups.websocket import RunsConsumer, SetupsConsumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter([
            re_path(r"^ws/runs/(?P<req_id>\d+)/$", RunsConsumer.as_asgi()),
            re_path(r"^ws/setups/$", SetupsConsumer.as_asgi()),
        ])
    ),
})