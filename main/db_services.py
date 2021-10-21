from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from .models import Chat, Message, MessageData
from .models import UserValidator, ChatValidator

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError


def get_all_users():
    """Returns all users <django.contrib.auth.models.User>"""
    return User.objects.all()


def get_all_chats():
    """Returns all chats <main.models.Chat>"""
    return Chat.objects.all()


def get_all_messages():
    """Returns all messages <main.models.Message"""
    return Message.objects.all()


def get_user_by_params(*args, **kwargs):
    """Gets user <django.contrib.auth.models.User>, if user with this
    kwargs doesn't exist, returns None"""
    try:
        return User.objects.get(**kwargs)
    except ObjectDoesNotExist:
        return None


def get_chat_by_params(**kwargs):
    """Returns chat <main.models.Chat> by params, if chat is not found, returns None"""
    try:
        return Chat.objects.get(**kwargs)
    except ObjectDoesNotExist:
        return None


def get_message_by_params(**kwargs):
    """Returns message <main.models.Message> by params, if message is not found, returns None"""
    try:
        return Message.objects.get(**kwargs)
    except ObjectDoesNotExist:
        return None


def get_session_by_params(**kwargs):
    """Returns session <django.contrib.sessions.models> by params, if session if not found, returns None"""
    try:
        return Session.objects.get(**kwargs)
    except ObjectDoesNotExist:
        return None


def create_user_by_params(*args, **kwargs):
    """Creates and returns user <django.contrib.auth.models.User>, if user is not
    valid, raises validation exception"""
    try:
        user = User(*args, **kwargs)
        UserValidator.validate_user(user)
        user.save()
        return user
    except ValidationError as e:
        raise e


def create_message_data_by_params(**kwargs):
    """Creates message data <main.models.MessageData>, if message data is not
    valid, raises validataion exception"""
    try:
        md = MessageData(**kwargs)
        md.save()
        return md
    except ValidationError as e:
        raise e


def create_message_by_params(*args, **kwargs):
    """Creates and returns message <main.models.Message>, if message is not
    valid, raises validation exception"""
    try:
        message = Message(*args, **kwargs)
        message.save()
        return message
    except ValidationError as e:
        raise e


def filter_user_by_params(**kwargs):
    """Returns users that suite specified filter"""
    users = User.objects.filter(**kwargs)
    return users


def filter_chat_by_params(**kwargs):
    """Returns chats that suite specified filter"""
    chats = Chat.objects.filter(**kwargs)
    return chats


def filter_message_by_params(**kwargs):
    """Filters messages that suite specified filter"""
    messages = Message.objects.filter(**kwargs)
    return messages



