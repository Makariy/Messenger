import json
from django.template import loader

from channels.generic.websocket import WebsocketConsumer, AsyncWebsocketConsumer
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer

from .models import Chat, Message, MessageData

from .db_services import *
from .db_services import get_last_messages
from .layers import *


class MessengerConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        self.commands = {
            'send_mes': self.dispatch_send_message,
            'del': self.dispatch_del_message,
            'pull_mes': self.dispatch_pull_message,
        }

        super().__init__(*args, **kwargs)

    def connect(self):
        try:
            self.user = self.scope['user']
            chat_id = self.scope['session'].get('chat_id')
            self.chat = Chat.objects.get(id=int(chat_id))

            users = list(self.chat.users.all())

            if self.user in users:
                self.user_group_name = messenger_get_group_name_for_user(self.user.id)
                self.group_name = messenger_get_group_name_for_chat(self.chat.id)
                async_to_sync(self.channel_layer.group_add)(self.user_group_name, self.channel_name)
                async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
                self.accept()
                return

        except (ValueError, ObjectDoesNotExist, Exception) as e:
            print(e)
        # NOT accepting if hadn't passed the validation

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

    def handle_send_message(self, event):
        template = loader.get_template('main/message.html')
        event['message']['user_id'] = self.user.id
        result = str(template.render(event['message']))
        self.send(json.dumps({
            'command': 'get_mes',
            'data': result
        }))

    def handle_del_message(self, event):
        self.send(json.dumps({
            'command': 'del',
            'data': event['message']['message_id'],
        }))

    def handle_chat_updated(self, event):
        if self.user.id not in event['message']['users_ids']:
            self.send(json.dumps({
                'command': 'disconnect'
            }))
            self.disconnect(1)

    def handle_chat_deleted(self, event):
        self.disconnect(1)

    def dispatch_send_message(self, data):
        data = MessageData(text=data['data'])
        if len(data.text) > 1024:
            return
        data.save()

        message = Message(author=self.user, chat=self.chat, data=data, type='text')
        message.save()

    def dispatch_del_message(self, data):
        try:
            message = get_message_by_params(id=data['data'])
            if self.user == message.author:
                message.delete()

        except Exception as e:
            print('Exception during deleting message: ', str(e))

    def dispatch_pull_message(self, data):
        try:
            last_id = data['last_id']
            last_messages = get_last_messages(chat=self.chat, last_id=int(last_id), count=20)
            template = loader.get_template('main/messages.html')
            self.send(json.dumps({
                'command': 'pull_mes',
                'data': str(template.render({
                    'messages': last_messages,
                    'user': self.user,
                }))
            }))
        except Exception as e:
            print('Error during pulling messages: ', str(e))

    def receive(self, text_data=None, bytes_data=None):
        data = json.loads(text_data)
        func = self.commands.get(data['command'])
        if func:
            try:
                func(data)
            except Exception as e:
                print(e)


class ChatConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope['user']

        if self.user and not self.user.is_anonymous:
            async_to_sync(self.channel_layer.group_add)(chat_get_group_name_for_user(self.user.id), self.channel_name)
            self.chats = list(filter_chat_by_params(users=self.user))
            for chat in self.chats:
                async_to_sync(self.channel_layer.group_add)(chat_get_group_name_for_chat(chat.id), self.channel_name)

            self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(chat_get_group_name_for_user(self.user.id), self.channel_name)
        for chat in self.chats:
            async_to_sync(self.channel_layer.group_discard)(chat_get_group_name_for_chat(chat.id), self.channel_name)

    def handle_message_created(self, event):
        try:
            message = event['message']
            md = message.data
            if message.type == 'text':
                data = md.text
            elif message.type == 'image':
                data = 'Image'
            elif message.type == 'video':
                data = 'Video'
            else:
                data = 'File'

            self.send(json.dumps({
                'command': 'message',
                'message': data,
                'author': message.author.username,
                'chat_id': message.chat.id,
            }))
        except Exception as e:
            print('Exception during notifying chats: ', str(e))

    def handle_message_deleted(self, event):
        message = event['message']
        if message.get('id') is not None:
            self.send(json.dumps({
                'command': 'delete_message',
                'author': message['author'],
                'message': message['message'],
                'chat_id': message['chat_id'],
                'id': message['id']
            }))
        else:
            self.send(json.dumps({
                'command': 'delete_message',
                'author': None,
                'message': None,
                'chat_id': message['chat_id'],
                'id': None
            }))

    def handle_chat_updated(self, event):
        message = event['message']
        chat = get_chat_by_params(id=message['chat_id'])

        if self.user.id not in message['users_ids']:
            self.send(json.dumps({
                'command': 'remove_chat',
                'chat_id': message['chat_id'],
            }))
            self.chats.remove(chat)
            async_to_sync(self.channel_layer.group_discard)(chat_get_group_name_for_chat(chat.id), self.channel_name)
        else:
            if chat not in self.chats:
                self.chats.append(chat)
                async_to_sync(self.channel_layer.group_add)(chat_get_group_name_for_chat(chat.id), self.channel_name)
                async_to_sync(self.channel_layer.group_send)(chat_get_group_name_for_user(self.user.id), {
                    'type': 'handle_chat_created',
                    'message': message
                })
            self.send(json.dumps({
                'command': 'update_chat',
                'last_message': message['last_message'],
                'chat_id': message['chat_id'],
                'chat_title': message['chat_title']
            }))

    def handle_chat_deleted(self, event):
        self.send(json.dumps({
            'command': 'remove_chat',
            'chat_id': event['message']['chat_id']
        }))

    def handle_chat_created(self, event):
        message = event['message']

        chat = get_chat_by_params(id=message['chat_id'])
        self.chats.append(chat)
        self.send(json.dumps({
            'command': 'create_chat',
            'chat_title': message['chat_title'],
            'chat_id': message['chat_id'],
            'last_message': message.get('last_message'),
        }))
        async_to_sync(self.channel_layer.group_add)(chat_get_group_name_for_chat(message['chat_id']), self.channel_name)

    def receive(self):
        pass
