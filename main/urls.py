from django.urls import path

from .views import MessagesPage
from .views import Authorization
from .views import Registration
from .views import ChatsHandler
from .views import ChatsCreator
from .views import UserSettings
from .views import request_session_id
from .views import FileHandler


messages_page = MessagesPage()
authorization_page = Authorization()
registration_page = Registration()
chats_handler = ChatsHandler()
chats_creator = ChatsCreator()
user_settings = UserSettings()
file_handler = FileHandler()

urlpatterns = [
	path('', messages_page.handle, name='messages_page'),
	path('login/', authorization_page.handle, name='login'),
	path('signup/', registration_page.handle, name='signup'),
	path('chats/', chats_handler.handle, name='chats_handler'),
	path('create/', chats_creator.handle, name='create_chat'),
	path('user_settings/', user_settings.handle, name='user_settings'),
	path('get_session_id/', request_session_id, name='session_id'),
	path('file_upload/', file_handler.handle, name='file_handler'),
]