from django.test import TestCase
from django.test.client import Client
from django.http.cookie import SimpleCookie

from .models import User, Chat, Message
from .routine import StringHasher

from .views import *

import datetime

# Create your tests here.


class UserTest(TestCase):
    def setUp(self):
        self.user = User(name='TestUser', password='TestPassword', mail='testmail@gmail.com')
        self.user.save()

        self.chat = Chat(title='TestChat')
        self.chat.save()
        self.chat.users.add(self.user)

    def register(self, client):
        return client.post('/signin', data={'name': self.user.name, 'password': self.user.password}, follow=True)

    def test_1_user_can_login(self):
        request = self.register(self.client)

        # Assert it was the right function and the user was registered
        self.assertEquals(request.resolver_match.func.__name__, Authorization.handle.__name__)
        self.assertEquals(self.user.name, self.client.cookies.get('user_name').value)
        self.assertEquals(StringHasher.get_hash(self.user.password), self.client.cookies.get('user_password').value)

    def test_2_user_can_send_message(self):
        self.register(self.client)

        # Assert it was the right function and the user got the chat
        request = self.client.get('/chats?action=get_chat&chat_name=' + self.chat.title)
        self.assertEquals(request.resolver_match.func.__name__, ChatsHandler.handle.__name__)
        self.assertEquals(self.client.cookies.get('chat_name').value, self.chat.title)

        # Assert it was the right function and the user sent the message
        request = self.client.post('/request', data={'message': 'Hello'})
        self.assertEquals(request.resolver_match.func.__name__, MessagesHandler.handle.__name__)
        self.assertEquals(Message.objects.all().last().message, 'Hello')
        self.assertEquals(Message.objects.all().last().author, self.user)
        self.assertEquals(Message.objects.all().last().chat, self.chat)

    def test_3_user_can_create_chat(self):
        self.register(self.client)

        # Assert it was the right function and the chat was created
        request = self.client.post('/create', data={'title': 'TestCreatedChat', 'users': ['13', '14']})
        self.assertEquals(request.resolver_match.func.__name__, ChatsCreator.handle.__name__)
        self.assertEquals(Chat.objects.all().last().title, 'TestCreatedChat')
        self.assertEquals(self.user, Chat.objects.all().get(title='TestCreatedChat').users.first())

