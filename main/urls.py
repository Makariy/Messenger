from django.urls import path

from .views import MessagesPage
from .views import Authorization
from .views import Registration
from .views import ChatsHandler
from .views import ChatsCreator
from .views import UserSettings
from .views import FileHandler
from .views import ChatSettings


urlpatterns = [
	path('', MessagesPage.as_view(), name='messages_page'),
	path('login/', Authorization.as_view(), name='login'),
	path('signup/', Registration.as_view(), name='signup'),
	path('chats/', ChatsHandler.as_view(), name='chats_handler'),
	path('create/', ChatsCreator.as_view(), name='create_chat'),
	path('user_settings/', UserSettings.as_view(), name='user_settings'),
	path('file_upload/', FileHandler.as_view(), name='file_handler'),
	path('chat_settings/', ChatSettings.as_view(), name='chat_settings'),
]