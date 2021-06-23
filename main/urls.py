from django.urls import path 

from .views import MainPage
from .views import MessagesHandler
from .views import Authorization
from .views import Registration
from .views import ChatsHandler
from .views import ChatsCreator


main_page = MainPage()
message_handler = MessagesHandler()
authorization_page = Authorization()
registration_page = Registration()
chats_handler = ChatsHandler()
chats_creator = ChatsCreator()

urlpatterns = [
	path('', main_page.handle, name='main'),
	path('signin', authorization_page.handle, name='login'),
	path('signup', registration_page.handle, name='signup'),
	path('request', message_handler.handle, name='message_handler'),
	path('chats', chats_handler.handle, name='chats_handler'),
	path('create', chats_creator.handle, name='create_chat')
]