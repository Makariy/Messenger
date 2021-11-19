from django.apps import AppConfig
import os
import threading


class MainConfig(AppConfig):
    name = 'main'

    def ready(self):
        if os.environ.get('RUN_MAIN', None) != "true":
            return
