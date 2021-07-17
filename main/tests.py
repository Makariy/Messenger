from django.test import TestCase
from django.test.client import Client
from django.http.cookie import SimpleCookie
from django.core.exceptions import ObjectDoesNotExist

from .models import User, Chat, Message
from .routine import StringHasher

from .views import *

import sys

# Create your tests here.


def get_functions_class(func):
    return vars(sys.modules[func.__module__])[func.__qualname__.split('.')[0]]


def assert_not_raises(func, ex=BaseException, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except ex:
        return False
    return True


class UserTest(TestCase):
    def setUp(self):
        self.user = User(name='TestUser', password='TestPassword', mail='testmail@gmail.com')
        self.user.save()

        self.chat = Chat(title='TestChat')
        self.chat.save()
        self.chat.users.add(self.user)

    def login(self, client):
        return client.post('/signin', data={'name': self.user.name, 'password': self.user.password}, follow=True)

    def test_1_user_can_login(self):
        request = self.client.post('/signin', {'name': self.user.name, 'password': self.user.password})

        # Assert it was the right function and the user was registered right
        self.assertEquals(get_functions_class(request.resolver_match.func), Authorization)
        self.assertEquals(self.user.name, self.client.cookies.get('user_name').value)
        self.assertEquals(StringHasher.get_hash(self.user.password), self.client.cookies.get('user_password').value)

    def test_2_user_can_register(self):
        request = self.client.post('/signup', data={'name': 'TestRegisterUser', 'password': 'Test123321', 'mail': 'testregisteruser@gmail.com'}, follow=True)

        self.assertEquals(request.redirect_chain[-1], ('/chats', 302))
        self.assertEquals(assert_not_raises(User.objects.all().get, name='TestRegisterUser'), True)
        self.assertEquals(User.objects.all().get(name='TestRegisterUser').password, 'Test123321')
        self.assertEquals(User.objects.all().get(name='TestRegisterUser').mail, 'testregisteruser@gmail.com')


    def test_3_user_can_send_message(self):
        self.login(self.client)

        # Assert it was the right function and the user got the chat
        request = self.client.get('/chats?action=get_chat&chat_name=' + self.chat.title)
        self.assertEquals(get_functions_class(request.resolver_match.func), ChatsHandler)
        self.assertEquals(self.client.cookies.get('chat_name').value, self.chat.title)

        # Assert it was the right function and the user sent the message
        request = self.client.post('/request', data={'message': 'Hello'})
        self.assertEquals(get_functions_class(request.resolver_match.func), MessagesHandler)
        self.assertEquals(assert_not_raises(Message.objects.all().get, message='Hello'), True, msg="The message hadn't been created")
        self.assertEquals(Message.objects.all().last().author, self.user)
        self.assertEquals(Message.objects.all().last().chat, self.chat)

    def test_4_user_can_create_chat(self):
        self.login(self.client)
        second_user = User(name='TestUser2', password='TestUser2', mail='testmail2@gmail.com')
        second_user.save()

        # Assert it was the right function and the chat was created
        request = self.client.post('/create', data={'title': 'TestCreatedChat', 'users': [second_user.pk]})
        self.assertEquals(get_functions_class(request.resolver_match.func), ChatsCreator)
        self.assertEquals(assert_not_raises(Chat.objects.all().get, title='TestCreatedChat'), True, msg="The chat hadn't been created")
        self.assertEquals(second_user, Chat.objects.all().get(title='TestCreatedChat').users.first())
        self.assertEquals(self.user, Chat.objects.all().get(title='TestCreatedChat').users.last())

    def test_5_user_cant_register_wrong(self):
        request = self.client.post('/signup', data={'name': '', 'password': 'Test123321', 'mail': 'testregisteruser@gmail.com'}, follow=True)
        self.assertEquals(request.redirect_chain, [])
        request = self.client.post('/signup', data={'name': '', 'password': '', 'mail': 'testregisteruser@gmail.com'}, follow=True)
        self.assertEquals(request.redirect_chain, [])
        request = self.client.post('/signup', data={'name': 'TestCreatedChat', 'password': 'Test123321', 'mail': 'testregisteruser@gmail'}, follow=True)
        self.assertEquals(request.redirect_chain, [])

    def test_5_unknown_user_cant_send_message(self):
        self.client.cookies['chat_name'] = 'TestChat'
        request = self.client.post('/request', data={'message': 'Test'})
        self.assertEquals(request.url, '/')


    def test_6_user_cant_send_to_wrong_chat(self):
        self.login(self.client)
        self.client.cookies['chat_name'] = 'Chat'
        request = self.client.post('/request', data={'message': 'Test'})
        self.assertEquals(request.url, '/')
