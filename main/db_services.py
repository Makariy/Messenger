from .sock.server import WebSocketHandler, run_async

from django.contrib.auth.models import User
from .models import Chat, Message, MessageData
from .models import UserValidator, ChatValidator

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError


websocket_server = WebSocketHandler()


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

    for user in users:
        if websocket_server.get_chat().is_user_connected(user):
            run_async(websocket_server.get_chat().add_user_to_chat(user, chat))

    return chat


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


def delete_chat(chat: Chat):
    """Deletes chat. IMPORTANT!!! DOES NOT CHECK IF ADMIN IS DELETING
    THIS CHAT, so check it before calling this function"""
    websocket_server.get_chat().remove_chat(chat.id, list(chat.users.all()))
    websocket_server.get_messenger().remove_chat(chat.id, list(chat.users.all()))
    chat.delete()


def update_chat(chat, title, users):
    """Sets chat's properties to values specified in kwargs,
    if new values are not valid, raises ValidationError"""
    chat_server = websocket_server.get_chat()
    messenger_server = websocket_server.get_messenger()

    chat.title = title
    try:
        ChatValidator.validate_chat(chat)
    except ValidationError as e:
        raise e

    chat_server.rename_chat(chat.id, title)

    for user in users:
        try:
            if user not in chat.users.all():
                chat.users.add(user)
                # If user is connected to chat_server, then notify him about new chat
                if chat_server.is_user_connected(user):
                    run_async(chat_server.add_user_to_chat(user, chat))

        except ObjectDoesNotExist:
            pass

    # Remove users
    for user in chat.users.all():
        try:
            if (user not in users) and (not user.id == chat.admin.id):
                chat.users.remove(user)
                # If user is connected to messenger_server, then stop notifying him
                if messenger_server.is_user_connected(user):
                    run_async(messenger_server.remove_user_from_chat(user, chat))
                # If user is connected to chat_server, then stop notifying him
                if chat_server.is_user_connected(user):
                    run_async(chat_server.remove_user_from_chat(user, chat))

        except ObjectDoesNotExist:
            pass

    chat.save()

