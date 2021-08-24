import asyncio
import json
import time
from websockets.exceptions import ConnectionClosedOK

from django.http.cookie import parse_cookie
from django.template import loader
from django.shortcuts import render

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session

from ..models import Chat, Message, MessageData
from ..routine import StringHasher


class Connection:
	def __init__(self, user, socket):
		self.user = user
		self.socket = socket

	user = None
	socket = None


async def run_sync(func):
	return await asyncio.get_event_loop().run_in_executor(None, func)


async def get_user(session_id):
	session = await run_sync(lambda: Session.objects.get(session_key=session_id))
	user = await run_sync(lambda: User.objects.get(id=session.get_decoded().get('_auth_user_id')))
	return user


def get_last_messages(chat=None, chat_title=None, count=10, start_index=0):
	if not chat_title and not chat:
		return None
	if chat:
		messages = Message.objects.filter(chat=chat).order_by('-id')[start_index:start_index+count:]
	if chat_title:
		messages = Message.objects.filter(chat__title=chat_title).order_by('-id')[start_index:start_index + count:]
	return messages[::-1]


class MessageServer():
	chats = {}		# Contains as a key all chats that are being monitored
					# and connections as their values

	class RegistrationError(Exception):
		def __init__(self, message):
			self.message = message

		def __str__(self):
			return str(self.message)

	def __init__(self):
		# Before any actions a websocket recieves a command to activate
		# the right function to handle the next request
		self.commands = {
			'send_mes': self.send_message,
			'pull_messages': self.pull_messages,
			'del': self.delete,
		}

	async def _register(self, websocket):
		'''
			Adds websocket to monitoring chats and active connections
		'''
		try:
			cookies = parse_cookie(await websocket.recv())

			user = await get_user(cookies['sessionid'])
			chat = await run_sync(lambda: Chat.objects.get(title=cookies.get('chat_name')))
			chats = await run_sync(lambda: tuple(Chat.objects.filter(users__username=user.username)))

			# Add user to correct chat query
			if chat in chats:
				connection = Connection(user=user, socket=websocket)
				if not self.chats.get(chat.title):
					self.chats[chat.title] = [connection,]
				else:
					self.chats[chat.title].append(connection)

				return connection, chat
		except:
			raise self.RegistrationError('Unknown error during registration')

	async def _unregister(self, connection, chat):
		'''
			Unregister websocket from chat query and active connections
		'''
		if chat:
			self.chats[chat.title].remove(connection)
		if connection:
			await connection.socket.close()

	async def unregister(self, user=None, chat=None, connection=None, code='DISCONNECTED'):
		if user and chat:
			connection = await self.get_connection_by_user(user, chat.title)

		if not chat:
			chat = await self.get_chat_by_connection(connection)
		self.chats[chat.title].remove(connection)

		if connection:
			await connection.socket.send(json.dumps({
				'command': 'disconnect',
				'code': code,
			}))

	async def send_message(self, connection, chat, request):
		data = MessageData(text=request['data'])
		await run_sync(data.save)

		message = Message(author=connection.user, chat=chat, data=data, type='text')
		await run_sync(message.save)

		for conn in self.chats[chat.title]:
			template = loader.get_template('main/messages.html')
			await connection.socket.send(json.dumps({
				'command': 'get_mes',
				'data': str(template.render({'messages': [message], 'user': connection.user})),
			}))

	async def pull_messages(self, connection, chat, request):
		messages_length = request.get('messages_length')
		last_messages = await run_sync(lambda: get_last_messages(chat=chat, start_index=int(messages_length)))
		template = loader.get_template('main/messages.html')
		await connection.socket.send(json.dumps({
			'command': 'pull_messages',
			'data': await run_sync(lambda: str(template.render({
				'messages': last_messages,
				'user': connection.user,
			})))
		}))


	async def delete(self, connection, chat, request):
		'''
			Deletes message from chat with stated chat_id
		'''
		try:
			message = await run_sync(lambda: Message.objects.get(id=int(request['data'])))
			if await run_sync(lambda: connection.user == message.author):
				await run_sync(message.delete)
				for _connection in self.chats[chat.title]:
					await _connection.socket.send(json.dumps({
						'command': 'del',
						'data': request['data'],
					}))
		except:
			pass

	async def notify_img(self, user, chat, file_id):
		'''
			Function is being called from FileHandler.
			Notifies every user in stated chat about new file
		'''
		for conn in self.chats[chat.title]:
			template = loader.get_template('main/messages.html')
			message = await run_sync(lambda: Message.objects.get(id=str(file_id)))
			html_img = await run_sync(lambda: template.render({'messages': [message], 'user': conn.user}))
			await conn.socket.send(json.dumps({
				'command': 'notify_img',
				'data': str(html_img)
			}))

	async def handle(self, websocket, path):
		'''
			Resiters user and handles his commands. Finally closes the connection
		'''
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
		except:
			pass
		finally:
			await self._unregister(connection, chat)

	async def get_connection_by_user(self, user, chat_title):
		for connection in self.chats[chat_title]:
			if connection.user.id == user.id:
				return connection
		return None

	async def get_chat_by_connection(self, connection):
		for chat in self.chats:
			if connection in self.chats[chat]:
				return await run_sync(lambda: Chat.objects.get(title=chat))
		return None

	def is_user_connected(self, user):
		for chat in self.chats:
			for connection in self.chats[chat]:
				if connection.user.id == user.id:
					return True
		return False


class ChatServer:
	chats = {}
	connections = []
	is_monitoring = False

	def is_monitoring_empty(self):
		for chat in self.chats:
			if not len(self.chats[chat]) == 0:
				return False
		return True

	async def notify(self, chat_title):
		try:
			chat_id = await run_sync(lambda: Chat.objects.get(title=chat_title).id)
			db_message = await run_sync(lambda: Message.objects.filter(chat__title=chat_title).order_by('pk').last())

			if db_message:
				author_name = await run_sync(lambda: db_message.author.username)
				if db_message.type == 'text':
					message = await run_sync(lambda: db_message.data.text)
				else:
					message = 'Photo'
				data = str(author_name) + ': ' + str(message)
			else:
				data = 'There are no messages right now. You can be first to write something!'
			for connection in self.chats[chat_title]:
				await connection.socket.send(json.dumps({
					'command': 'update_message',
					'chat_id': str(chat_id),
					'chat_title': chat_title,
					'data': data,
				}))
		except:
			pass

	async def register(self, websocket):
		cookies = parse_cookie(await websocket.recv())

		user = await get_user(cookies.get('sessionid'))
		chats = await run_sync(lambda: tuple(Chat.objects.filter(users=user)))
		for chat in chats:
			users = self.chats.get(chat.title)
			connection = Connection(user=user, socket=websocket)
			if not users:
				self.chats[chat.title] = [connection]
			else:
				self.chats[chat.title].append(connection)
			self.connections.append(connection)

		return connection

	async def unregister(self, connection):
		for chat in self.chats:
			if connection in self.chats[chat]:
				self.chats[chat].remove(connection)
		self.connections.remove(connection)

		if self.is_monitoring_empty():
			self.is_monitoring = False

	async def monitor(self):
		while True:
			if not self.is_monitoring:
				break
			last_check = time.time()
			for chat in self.chats:
				await self.notify(chat)
			time_to_sleep = 0.5 - (time.time() - last_check)
			if time_to_sleep > 0:
				await asyncio.sleep(time_to_sleep)
			else:
				pass

	async def handle(self, websocket, path):
		connection = None
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
		except:
			pass
		finally:
			if connection is not None:
				await self.unregister(connection)

	async def remove_user_from_chat(self, user, chat):
		for connection in self.chats[chat.title]:
			if connection.user.id == user.id:
				self.chats[chat.title].remove(connection)
				await connection.socket.send(json.dumps({
					'command': 'remove_chat',
					'chat_id': chat.id,
				}))
				return True
		return False

	async def add_user_to_chat(self, user, chat):
		for connection in self.connections:
			if connection.user.id == user.id:
				last_message = await run_sync(lambda: Message.objects.filter(chat__title=chat.title).order_by('id').last())
				template = loader.get_template('main/chat.html')
				await connection.socket.send(json.dumps({
					'command': 'add_chat',
					'data': await run_sync(lambda: str(template.render({
						'chat': chat,
						'data': last_message,
					})))
				}))
				if self.chats.get(chat.title):
					self.chats[chat.title] = [connection]
				else:
					self.chats[chat.title].append(connection)
				return

	def is_user_connected(self, user):
		for connection in self.connections:
			if connection.user.id == user.id:
				return True
		return False

	def rename_chat(self, before, now):
		if self.chats.get(before):
			connections = self.chats[before]
			self.chats.pop(before)
			self.chats[now] = connections
