from django.urls import path

from .consumers import MessengerConsumer
from .consumers import ChatConsumer


ws_urlpatterns = [
    path('messages/', MessengerConsumer.as_asgi()),
    path('chats/', ChatConsumer.as_asgi()),
]
