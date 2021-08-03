from django.test import TestCase
from django.test.client import Client
from django.http.cookie import SimpleCookie
from django.core.exceptions import ObjectDoesNotExist

from .models import Chat, Message
from .routine import StringHasher

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session

from .views import *

import sys

# Create your tests here.


def get_functions_class(func):
    return vars(sys.modules[func.__module__])[func.__qualname__.split('.')[0]]


def not_raises(func, ex=BaseException, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except ex:
        return False
    return True


class UserTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='TestUser', password='TestPassword', email='testmail@gmail.com')

        self.chat = Chat(title='TestChat')
        self.chat.save()
        self.chat.users.add(self.user)

