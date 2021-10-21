from .sock.server import WebSocketHandler, run_async
from .models import Chat, ChatValidator

from django.core.exceptions import ObjectDoesNotExist, ValidationError


websocket_server = WebSocketHandler()


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
                    run_async(chat_server.add_user_to_chat(user, chat.id))

        except ObjectDoesNotExist:
            pass

    # Remove users
    for user in chat.users.all():
        try:
            if (user not in users) and (not user.id == chat.admin.id):
                chat.users.remove(user)
                # If user is connected to messenger_server, then stop notifying him
                if messenger_server.is_user_connected(user):
                    run_async(messenger_server.remove_user_from_chat(user, chat.id))
                # If user is connected to chat_server, then stop notifying him
                if chat_server.is_user_connected(user):
                    run_async(chat_server.remove_user_from_chat(user, chat.id))

        except ObjectDoesNotExist:
            pass

    chat.save()

