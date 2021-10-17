import asyncio
import os
import threading
import websockets
import json
import time
from websockets.exceptions import ConnectionClosedOK

from django.core.exceptions import ObjectDoesNotExist
from django.http.cookie import parse_cookie
from django.template import loader
from django.shortcuts import render

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session

from ..models import Chat, Message, MessageData
from ..messages_service import get_last_messages


async def run_sync(func):
    return await asyncio.get_event_loop().run_in_executor(None, func)


def run_async(func):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
        loop = asyncio.get_event_loop()

    return loop.run_until_complete(func)


class Connection:
	def __init__(self, user, socket):
		self.user = user
		self.socket = socket

	user = None
	socket = None


async def get_user(session_id):
	session = await run_sync(lambda: Session.objects.get(session_key=session_id))
	user = await run_sync(lambda: User.objects.get(id=session.get_decoded().get('_auth_user_id')))
	return user


class MessageServer():
	chats = {}		# Contains as a key all chat ids that are being monitored
					# and connections as their values

	class RegistrationError(Exception):
		def __init__(self, message):
			self.message = message

		def __str__(self):
			return str(self.message)

	def __init__(self):
		# Before any actions a websocket receives a command to activate
		# the right function to handle a request
		self.commands = {
			'send_mes': self.send_message,
			'pull_messages': self.pull_messages,
			'del': self.delete,
		}

	async def _register(self, websocket):
		try:
			cookies = parse_cookie(await websocket.recv())

			try: 	user = await get_user(cookies['sessionid'])
			except ObjectDoesNotExist: raise self.RegistrationError('User with this name doesn\'t exist')
			try: 	chat = await run_sync(lambda: Chat.objects.get(id=cookies.get('chat_id')))
			except ObjectDoesNotExist: raise self.RegistrationError('Chat with this name doesn\'t exist')

			chats = await run_sync(lambda: tuple(Chat.objects.filter(users__id=user.id)))

			# Add user to correct chat query
			if chat in chats:
				connection = Connection(user=user, socket=websocket)
				if not self.chats.get(chat.id):
					self.chats[chat.id] = [connection,]
				else:
					self.chats[chat.id].append(connection)

				return connection, chat
			else:
				raise self.RegistrationError('The user is not a member of this chat')

		except self.RegistrationError as e:
			raise e

	async def _unregister(self, connection, chat):
		if chat and chat.id in self.chats and connection in self.chats[chat.id]:
			self.chats[chat.id].remove(connection)
		if connection:
			await connection.socket.close()

	async def remove_user_from_chat(self, user=None, chat_id=None, connection=None, code='DISCONNECTED'):
		if user and chat_id:
			connection = await self.get_connection_by_user(user, chat_id)

		if not chat_id:
			chat = await self.get_chat_by_connection(connection)
		if connection in self.chats[chat.id]:
			self.chats[chat_id].remove(connection)

		if connection:
			await connection.socket.send(json.dumps({
				'command': 'disconnect',
				'code': code,
			}))

	async def send_message(self, connection, chat, request):
		try:
			data = MessageData(text=request['data'])
			if len(data.text) > 1024:
				return
			await run_sync(data.save)

			message = Message(author=connection.user, chat=chat, data=data, type='text')
			await run_sync(message.save)

			for conn in self.chats[chat.id]:
				template = loader.get_template('main/messages.html')
				await conn.socket.send(json.dumps({
					'command': 'get_mes',
					'data': str(template.render({
						'messages': [message],
						'user': conn.user
					})),
				}))
		except Exception as e:
			print('Error during sending message: ', str(e))

	async def pull_messages(self, connection, chat, request):
		try:
			last_id = request.get('last_id')
			last_messages = await run_sync(lambda: get_last_messages(chat=chat, last_id=int(last_id), count=20))
			template = loader.get_template('main/messages.html')
			await connection.socket.send(json.dumps({
				'command': 'pull_messages',
				'data': await run_sync(lambda: str(template.render({
					'messages': last_messages,
					'user': connection.user,
				})))
			}))
		except Exception as e:
			print('Error during pulling messages: ', str(e))

	async def delete(self, connection, chat, request):
		try:
			message = await run_sync(lambda: Message.objects.get(id=int(request['data'])))
			if await run_sync(lambda: connection.user == message.author):
				await run_sync(message.delete)
				for _connection in self.chats[chat.id]:
					await _connection.socket.send(json.dumps({
						'command': 'del',
						'data': request['data'],
					}))
		except Exception as e:
			print('Exception during deleting message: ', str(e))

	async def notify_file(self, user, chat, file_id):
		try:
			for conn in self.chats[chat.id]:
				template = loader.get_template('main/messages.html')
				message = await run_sync(lambda: Message.objects.get(id=str(file_id)))
				html_file = await run_sync(lambda: template.render({'messages': [message], 'user': conn.user}))
				await conn.socket.send(json.dumps({
					'command': 'notify_file',
					'type': message.type,
					'data': str(html_file)
				}))
		except Exception as e:
			print('Error during notifying file: ', str(e))

	async def handle(self, websocket, path):
		connection = None
		chat = None
		try:
			connection, chat = await self._register(websocket)

			while True:
				message = json.loads(await websocket.recv())
				func = self.commands.get(message['command'])
				if func:
					await func(connection, chat, message)
		except ConnectionClosedOK:
			pass
		except self.RegistrationError as e:
			print('Error during user registration: ', str(e))
		except Exception as e:
			print('Unknown error during handle: ', str(e))
		finally:
			await self._unregister(connection, chat)

	async def get_connection_by_user(self, user, chat_id=None):
		if chat_id:
			for connection in self.chats[chat_id]:
				if connection.user.id == user.id:
					return connection
		else:
			for _id in self.chats:
				for connection in self.chats[_id]:
					if connection.user.id == user.id:
						return connection
		return None

	async def get_chat_by_connection(self, connection):
		for chat_id in self.chats:
			if connection in self.chats[chat_id]:
				return await run_sync(lambda: Chat.objects.get(id=chat_id))
		return None

	def is_user_connected(self, user, chat=None, chat_id=None):
		if chat or chat_id:
			if chat:
				chat_id = chat.id
			for connection in self.chats[chat_id]:
				if connection.user.id == user.id:
					return True

		for _id in self.chats:
			for connection in self.chats[_id]:
				if connection.user.id == user.id:
					return True
		return False

	async def remove_users_from_chat(self, users, chat_id):
		for user in users:
			await self.remove_user_from_chat(user, chat_id)

	def remove_chat(self, chat_id: int, users: list):
		if chat_id in self.chats:
			run_async(self.remove_users_from_chat(users, chat_id))
			self.chats.pop(chat_id)


class ChatServer:
	chats = {}
	connections = []
	is_monitoring = False
	lock = threading.Lock()

	def is_monitoring_empty(self):
		for chat in self.chats:
			if not len(self.chats[chat]) == 0:
				return False
		return True

	async def notify(self, chat_id, db_message):
		try:
			if db_message:
				author_name = await run_sync(lambda: db_message.author.username)
				if db_message.type == 'text':
					message = await run_sync(lambda: db_message.data.text)
				else:
					message = 'Photo'
				data = str(author_name) + ': ' + str(message)
			else:
				data = 'There are no messages right now. You can be first to write something!'
			for connection in self.chats[chat_id]:
				await connection.socket.send(json.dumps({
					'command': 'update_message',
					'chat_id': str(chat_id),
					'data': data,
				}))
		except Exception as e:
			print('Exception during notifying chats: ', str(e))

	async def register(self, websocket):
		msg = await websocket.recv()
		cookies = parse_cookie(msg)

		user = await get_user(cookies.get('sessionid'))
		connection = Connection(user=user, socket=websocket)

		chats = await run_sync(lambda: tuple(Chat.objects.filter(users=user)))
		for chat in chats:
			if not self.chats.get(chat.id):
				self.chats[chat.id] = [connection]
			else:
				self.chats[chat.id].append(connection)

		self.connections.append(connection)
		return connection

	async def unregister(self, connection):
		for chat_id in self.chats:
			if connection in self.chats[chat_id]:
				self.chats[chat_id].remove(connection)
		if connection in self.connections:
			self.connections.remove(connection)

		if self.is_monitoring_empty():
			self.is_monitoring = False

	async def monitor(self):
		while True:
			if not self.is_monitoring:
				break
			self.lock.acquire()
			last_check = time.time()

			for chat_id in self.chats:
				db_message = await run_sync(lambda: Message.objects.filter(chat__id=chat_id).order_by('pk').last())
				await self.notify(chat_id, db_message)

			self.lock.release()
			time_to_sleep = 0.5 - (time.time() - last_check)
			if time_to_sleep > 0:
				await asyncio.sleep(time_to_sleep)
			else:
				pass

	async def handle(self, websocket, path):
		try:
			connection = await self.register(websocket)
			if not self.is_monitoring:
				if not self.is_monitoring_empty():
					asyncio.get_event_loop().create_task(self.monitor())
					self.is_monitoring = True

			while True:
				if not connection.socket.closed:
					await asyncio.sleep(1)
				else:
					break
		except ConnectionClosedOK:
			pass
		except Exception as e:
			print('Unknown exception during handling chat')
		finally:
			if connection:
				await self.unregister(connection)

	async def remove_user_from_chat(self, user, chat_id):
		try:
			self.lock.acquire()
			for connection in self.chats[chat_id]:
				if connection.user.id == user.id:
					self.chats[chat_id].remove(connection)
					await connection.socket.send(json.dumps({
						'command': 'remove_chat',
						'chat_id': chat_id,
					}))
					return True
		finally:
			self.lock.release()
		return False

	async def remove_users_from_chat(self, users, chat_id):
		for user in users:
			if self.is_user_connected(user):
				await self.remove_user_from_chat(user, chat_id)

	async def add_user_to_chat(self, user, chat):
		try:
			self.lock.acquire()
			for connection in self.connections:
				if connection.user.id == user.id:
					last_message = await run_sync(lambda: Message.objects.filter(chat__id=chat.id).order_by('id').last())
					template = loader.get_template('main/chat.html')
					data = await run_sync(lambda: str(template.render({
						'chat': chat,
						'data': last_message,
					})))
					await connection.socket.send(json.dumps({
						'command': 'add_chat',
						'data': data
					}))
					if self.chats.get(chat.id):
						self.chats[chat.id].append(connection)
					else:
						self.chats[chat.id] = [connection]

					if connection not in self.connections:
						self.connections.append(connection)

					return
		finally:
			self.lock.release()

	def is_user_connected(self, user):
		for connection in self.connections:
			if connection.user.id == user.id:
				return True
		return False

	def rename_chat(self, _id, name):
		try:
			self.lock.acquire()
			if self.chats.get(_id):
				connections = self.chats[_id]
				for connection in connections:
					run_async(connection.socket.send(json.dumps({'command': 'rename_chat', 'id': _id, 'name': name})))
		finally:
			self.lock.release()

	def remove_chat(self, chat_id: int, users: list):
		if chat_id in self.chats:
			run_async(self.remove_users_from_chat(users=users, chat_id=chat_id))
			connections = self.chats.pop(chat_id)
			for connection in connections:
				self.connections.remove(connection)


class SingleWebSocketHandler:
	_instance = None

	def __new__(cls, *args, **kwargs):
		if not isinstance(cls._instance, cls):
			cls._instance = object.__new__(cls, *args, **kwargs)
		return cls._instance


class WebSocketHandler(SingleWebSocketHandler):
	def __init__(self):
		self.path = {
			'messenger': MessageServer(),
			'chat': ChatServer()
		}
		self.server_thread = threading.Thread(target=self._start_websocket)

	async def handle(self, websocket, path):
		server = self.path.get(await websocket.recv())
		if server:
			await server.handle(websocket, path)

	def start(self):
		if os.environ.get('RUN_MAIN', None) != 'true':
			return
		if not self.server_thread.is_alive():
			self.server_thread.start()

	def _start_websocket(self):
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		start_server = websockets.serve(self.handle, '0.0.0.0', 8001)
		loop.run_until_complete(start_server)

		if not loop.is_running():
			loop.run_forever()

	def get_chat(self):
		return self.path.get('chat')

	def get_messenger(self):
		return self.path.get('messenger')


