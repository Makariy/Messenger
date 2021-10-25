from django.test import TestCase
from django.test.client import Client
from django.http.cookie import SimpleCookie
from django.core.exceptions import ObjectDoesNotExist

from .models import Chat, Message

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session

from .views import *


from .db_services import get_all_users
from .db_services import get_all_chats
from .db_services import get_all_messages
from .db_services import get_user_by_params
from .db_services import get_chat_by_params
from .db_services import get_message_by_params
from .db_services import create_user_by_params
from .runtime_services import create_chat_by_params
from .db_services import create_message_data_by_params
from .db_services import create_message_by_params
from .db_services import filter_user_by_params
from .db_services import filter_message_by_params
from .runtime_services import delete_chat
from .runtime_services import update_chat


import sys

# Create your tests here.


def get_functions_class(func):
    return vars(sys.modules[func.__module__])[func.__qualname__.split('.')[0]]


def assert_raises(func, ex=BaseException, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except Exception:
        return True
    return False


class DBServicesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='TestUser', password='TestPassword', email='testmail@gmail.com')

        self.chat = Chat(title='TestChat', admin=self.user)
        self.chat.save()
        self.chat.users.add(self.user)

        self.md = MessageData.objects.create(text="Test message")
        self.message = Message.objects.create(author=self.user, chat=self.chat, data=self.md, type='text')

    """Getting all objects test"""
    def test_get_all_users(self):
        self.assertEquals(list(User.objects.all()), list(get_all_users()), msg='Function get_all_users failed')

    def test_get_all_chats(self):
        self.assertEquals(list(Chat.objects.all()), list(get_all_chats()), msg='Function get_all_chats failed')

    def test_get_all_messages(self):
        self.assertEquals(list(Message.objects.all()), list(get_all_messages()), msg='Function get_all_messages failed')

    """Getting objects by parameters test"""
    def test_get_user_by_params(self):
        self.assertEquals(User.objects.get(id=self.user.id), get_user_by_params(id=self.user.id))
        self.assertEquals(None, get_user_by_params(id=-1))

    def test_get_chat_by_params(self):
        self.assertEquals(Chat.objects.get(id=self.chat.id), get_chat_by_params(id=self.chat.id))
        self.assertEquals(None, get_chat_by_params(id=-1))

    def test_get_message_by_params(self):
        self.assertEquals(Message.objects.get(id=self.message.id), get_message_by_params(id=self.message.id))
        self.assertEquals(None, get_message_by_params(id=-1))

    """Creating objects by parameters test"""
    def test_create_user_by_params(self):
        self.assertEquals(True, assert_raises(create_user_by_params,
                                            username=self.user.username,
                                            password='Testnormalpassword123',
                                            email='testnormalemail@gmail.com'))
        self.assertEquals(True, assert_raises(create_user_by_params,
                                            username='Testnamesameaspassword',
                                            password='Testnamesameaspassword',
                                            email='testnormalemail@gmail.com'))
        self.assertEquals(True, assert_raises(create_user_by_params,
                                            username='Testnormalname',
                                            password='Testnormalpassword',
                                            email=self.user.email))
        self.assertEquals(False, assert_raises(create_user_by_params,
                                            username='Testnormalname',
                                            password='Testnormalpassword',
                                            email='testnormalemail@gmail.com'))
        self.assertEquals(False, assert_raises(User.objects.get, username='Testnormalname'))
        user = User.objects.get(username='Testnormalname')
        self.assertEquals(user.email, 'testnormalemail@gmail.com')
        self.assertEquals(False, assert_raises(lambda: user.delete()))

    def test_create_chat_by_params(self):
        self.assertEquals(True, assert_raises(create_chat_by_params,
                                              title='a',
                                              admin=self.user,
                                              users=[]))
        self.assertEquals(False, assert_raises(create_chat_by_params,
                                               title='Test chat',
                                               admin=self.user,
                                               users=[]))
        self.assertEquals(False, assert_raises(Chat.objects.get, title='Test chat'))
        chat = Chat.objects.get(title='Test chat')
        self.assertNotEquals(None, chat.id)
        self.assertEquals([self.user,], list(chat.users.all()))
        self.assertEquals(chat.admin, self.user)

        self.assertEquals(False, assert_raises(lambda: chat.delete()))

    def test_create_message_data_by_params(self):
        test_message = 'Test message data test_create_message_data_by_params'
        self.assertEquals(False, assert_raises(create_message_data_by_params,
                                               text=test_message))
        self.assertEquals(False, assert_raises(MessageData.objects.get,
                                               text=test_message))
        self.assertEquals(False, assert_raises(MessageData.objects.
                                               get(text=test_message)
                                               .delete))

    def test_create_message_by_params(self):
        test_message = 'Test message data test_create_message_by_params'
        md = create_message_data_by_params(text=test_message)
        self.assertEquals(False, assert_raises(create_message_by_params, author=self.user,
                                               chat=self.chat,
                                               data=md,
                                               type='text'))
        self.assertEquals(False, assert_raises(Message.objects.get, data__text=test_message))
        message = Message.objects.get(data__text=test_message)
        self.assertEquals(message.author, self.user)
        self.assertEquals(message.chat, self.chat)
        self.assertEquals(message.data, md)
        self.assertEquals(False, assert_raises(message.delete))

    def test_filter_user_by_params(self):
        self.assertEquals(list(User.objects.filter(username=self.user.username)),
                          list(filter_user_by_params(username=self.user.username)))

    def test_filter_chat_by_params(self):
        self.assertEquals(list(Chat.objects.filter(title=self.chat.title)),
                          list(filter_chat_by_params(title=self.chat.title)))

    def test_filter_message_by_params(self):
        self.assertEquals(list(Message.objects.filter(author=self.user)),
                          list(filter_message_by_params(author=self.user)))

    def test_delete_chat(self):
        chat = create_chat_by_params(title='Test chat test_delete_chat', admin=self.user, users=[])
        self.assertEquals(False, assert_raises(delete_chat, chat=chat))

    def test_update_chat(self):
        new_chat_title = 'Test update chat  test_update_chat'
        self.assertEquals(False, assert_raises(update_chat,
                                               chat=self.chat,
                                               title=new_chat_title,
                                               users=[]))
        self.assertEquals(False, assert_raises(get_chat_by_params, title=new_chat_title))
        chat = get_chat_by_params(title=new_chat_title)
        self.assertEquals(True, self.user in chat.users.all())
        self.assertEquals(chat.title, new_chat_title)
        self.assertEquals(chat.admin, self.user)


class ViewTest(TestCase):
    def setUp(self):
        self.user_password = 'TestPassword'
        self.user = User.objects.create_user(username='TestUser', password=self.user_password, email='testmail@gmail.com')

        self.chat = Chat(title='TestChat', admin=self.user)
        self.chat.save()
        self.chat.users.add(self.user)

        self.md = MessageData.objects.create(text="Test message")
        self.message = Message.objects.create(author=self.user, chat=self.chat, data=self.md, type='text')

    def test_user_can_login(self):
        response = self.client.post('http://127.0.0.1:8000/login/', data={
            'username': self.user.username,
            'password': self.user_password}, follow=True)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response.resolver_match.view_name, 'chats_handler')


