from django.apps import AppConfig
import os
import threading


class MainConfig(AppConfig):
    name = 'main'

    websocket_handler = None

    def ready(self):
        if os.environ.get('RUN_MAIN', None) != "true":
            return

        from .sock.server import WebSocketHandler

        self.websocket_handler = WebSocketHandler()
        self.websocket_handler.start()
