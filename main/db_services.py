from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from .models import Chat, Message, MessageData
from .models import UserValidator, ChatValidator

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError

from .layers import *


def get_last_messages(chat=None, chat_title=None, count=10, last_id=-1):
    """Returns last <count> starting from <last_id> (if specified) messages <main.models.Message>
     from <chat> or chat with title <chat_title>, if <chat> or <chat_title> is not specified, raises ValueError"""
    if not chat_title and not chat:
        raise ValueError('<chat_title> or <chat> not specified')

    if chat:
        messages = Message.objects.filter(chat=chat).order_by('-id')
    if chat_title:
        messages = Message.objects.filter(chat__title=chat_title).order_by('-id')

    start_index = 0
    if last_id is not -1:
        for i in range(len(messages)):
            if messages[i].id == int(last_id):
                start_index = i + 1
                break

    messages = messages[start_index:start_index+count]
    return messages[::-1]


def get_last_message(chat):
    """Returns the last message <main.models.Message> from chat <main.models.Chat>"""
    return Message.objects.filter(chat=chat).order_by('id').last()


def get_last_chats_messages(chats):
    """Returns the last messages <main.models.Message> from chats <chats>"""
    return [get_last_message(chat) for chat in chats]


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
        return User.objects.create_user(*args, **kwargs)
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


def create_chat_by_params(title, admin, users):
    """Creates chat by params"""
    try:
        chat = Chat(title=title, admin=admin)
        ChatValidator.validate_chat(chat)
        chat.save()
    except ValidationError as e:
        raise e
    chat.users.add(admin)
    for user in users:
        chat.users.add(user)

    channel = get_channel_layer()
    users_ids = [user.id for user in chat.users.all()]
    for user_id in users_ids:
        user_channel_name = chat_get_group_name_for_user(user_id)
        async_to_sync(channel.group_send)(user_channel_name, {
            'type': 'handle_chat_created',
            'message': {
                'chat_title': chat.title,
                'chat_id': chat.id,
                'users_ids': users_ids,
            }
        })

    return chat


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


def delete_chat(chat: Chat):
    """Deletes chat. IMPORTANT!!! DOES NOT CHECK IF ADMIN IS DELETING
    THIS CHAT, so check it before calling this function"""
    chat.delete()


def update_chat(chat, title, users):
    """Sets chat's properties to values specified in kwargs,
    if new values are not valid, raises ValidationError"""
    chat.title = title
    try:
        ChatValidator.validate_chat(chat)
    except ValidationError as e:
        raise e

    for user in users:
        try:
            if user not in chat.users.all():
                chat.users.add(user)
        except ObjectDoesNotExist:
            pass

    # Remove users
    for user in chat.users.all():
        try:
            if (user not in users) and (not user.id == chat.admin.id):
                chat.users.remove(user)
        except ObjectDoesNotExist:
            pass

    chat.save()


