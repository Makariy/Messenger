from .models import Message, Chat
from .db_services import *
from .layers import *

from django.db.models.signals import post_save, post_delete, pre_save
from asgiref.sync import sync_to_async, async_to_sync
from channels.layers import get_channel_layer


def render_message(message):
    if not message:
        raise ValueError('Message was None')
    if message.type == 'text':
        data = message.data.text
    elif message.type == 'image':
        data = 'Image'
    elif message.type == 'video':
        data = 'Video'
    else:
        data = 'File'
    return {
        'author': message.author.username,
        'author_id': message.author.id,
        'message': data,
        'type': message.type,
        'message_id': message.id,
        'chat_id': message.chat.id,
    }


def on_message_created(sender, instance: Message, **kwargs):
    channel = get_channel_layer()
    chat_channel_name = chat_get_group_name_for_chat(instance.chat.id)
    message_channel_name = messenger_get_group_name_for_chat(instance.chat.id)
    async_to_sync(channel.group_send)(chat_channel_name, {
        'type': 'handle_message_created',
        'message': render_message(instance)
    })
    async_to_sync(channel.group_send)(message_channel_name, {
        'type': 'handle_send_message',
        'message': render_message(instance)
    })


def on_message_delete(sender, instance: Message, **kwargs):
    channel = get_channel_layer()
    message_channel_name = messenger_get_group_name_for_chat(instance.chat.id)
    async_to_sync(channel.group_send)(message_channel_name, {
        'type': 'handle_del_message',
        'message': render_message(instance)
    })

    chat_channel_name = chat_get_group_name_for_chat(instance.chat.id)
    last_message = get_last_message(instance.chat)

    if last_message:
        message = render_message(last_message)
    else:
        message = {'chat_id': instance.chat.id}
    async_to_sync(channel.group_send)(chat_channel_name, {
        'type': 'handle_message_deleted',
        'message': message
    })


def on_chat_modified(sender, instance: Chat, **kwargs):
    if not kwargs['created']:
        channel = get_channel_layer()
        users_ids = [user.id for user in instance.users.all()]
        last_message = get_last_message(instance)

        for user in instance.users.all():
            chat_user_channel_name = chat_get_group_name_for_user(user.id)
            async_to_sync(channel.group_send)(chat_user_channel_name, {
                'type': 'handle_chat_updated',
                'message': {
                    'chat_title': instance.title,
                    'chat_id': instance.id,
                    'last_message': render_message(last_message) if last_message else None,
                    'users_ids': users_ids,
                }
            })

        messenger_chat_channel_name = messenger_get_group_name_for_chat(instance.id)
        chat_channel_name = chat_get_group_name_for_chat(instance.id)

        async_to_sync(channel.group_send)(messenger_chat_channel_name, {
            'type': 'handle_chat_updated',
            'message': {
                'users_ids': users_ids
            }
        })
        async_to_sync(channel.group_send)(chat_channel_name, {
            'type': 'handle_chat_updated',
            'message': {
                'chat_title': instance.title,
                'chat_id': instance.id,
                'last_message': render_message(last_message) if last_message else None,
                'users_ids': users_ids,
            }
        })


def on_chat_delete(sender, instance, **kwargs):
    channel = get_channel_layer()
    messenger_channel_name = messenger_get_group_name_for_chat(instance.id)
    chat_channel_name = chat_get_group_name_for_chat(instance.id)
    async_to_sync(channel.group_send)(messenger_channel_name, {
        'type': 'handle_chat_deleted',
        'message': {
            'chat_id': instance.id
        }
    })
    async_to_sync(channel.group_send)(chat_channel_name, {
        'type': 'handle_chat_deleted',
        'message': {
            'chat_id': instance.id
        }
    })


post_save.connect(on_message_created, sender=Message)
post_delete.connect(on_message_delete, sender=Message)

post_save.connect(on_chat_modified, sender=Chat)
post_delete.connect(on_chat_delete, sender=Chat)
