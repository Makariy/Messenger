import asyncio
import threading
import websockets
import json
import time
from websockets.exceptions import ConnectionClosedOK

from django.core.exceptions import ObjectDoesNotExist
from django.http.cookie import parse_cookie
from django.template import loader
from django.shortcuts import render

from server.settings import SECRET_KEY

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session

from ..models import Chat, Message, MessageData


class Connection:
	def __init__(self, user, socket):
		self.user = user
		self.socket = socket

	user = None
	socket = None


async def run_sync(func):
	return await asyncio.get_event_loop().run_in_executor(None, func)


def run_async(func):
	try:
		loop = asyncio.get_event_loop()
	except RuntimeError:
		asyncio.set_event_loop(asyncio.new_event_loop())
		loop = asyncio.get_event_loop()

	return loop.run_until_complete(func)


async def get_user(session_id):
	session = await run_sync(lambda: Session.objects.get(session_key=session_id))
	user = await run_sync(lambda: User.objects.get(id=session.get_decoded().get('_auth_user_id')))
	return user


def get_last_messages(chat=None, chat_title=None, count=10, last_id=-1):
	if not chat_title and not chat:
		return None

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


class MessageServer():
	chats = {}		# Contains as a key all chat titles that are being monitored
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
		'''
			Adds websocket to monitoring chats and active connections
		'''
		try:
			cookies = parse_cookie(await websocket.recv())

			try: 	user = await get_user(cookies['sessionid'])
			except 	ObjectDoesNotExist: raise self.RegistrationError('User with this name doesn\'t exist')
			try: 	chat = await run_sync(lambda: Chat.objects.get(title=cookies.get('chat_name')))
			except 	ObjectDoesNotExist: raise self.RegistrationError('Chat with this name doesn\'t exist')

			chats = await run_sync(lambda: tuple(Chat.objects.filter(users__id=user.id)))

			# Add user to correct chat query
			if chat in chats:
				connection = Connection(user=user, socket=websocket)
				if not self.chats.get(chat.title):
					self.chats[chat.title] = [connection,]
				else:
					self.chats[chat.title].append(connection)

				return connection, chat
			else:
				raise self.RegistrationError('The user is not a member of this chat')

		except self.RegistrationError:
			raise

		raise self.RegistrationError('Unknown error during registration')

	async def _unregister(self, connection, chat):
		'''
			Unregister websocket from chat query and active connections
		'''
		if chat and chat.title in self.chats and connection in self.chats[chat.title]:
			self.chats[chat.title].remove(connection)
		if connection:
			await connection.socket.close()

	async def remove_user_from_chat(self, user=None, chat=None, connection=None, code='DISCONNECTED'):
		if user and chat:
			connection = await self.get_connection_by_user(user, chat.title)

		if not chat:
			chat = await self.get_chat_by_connection(connection)
		if connection in self.chats[chat.title]:
			self.chats[chat.title].remove(connection)

		if connection:
			await connection.socket.send(json.dumps({
				'command': 'disconnect',
				'code': code,
			}))

	async def send_message(self, connection, chat, request):
		try:
			data = MessageData(text=request['data'])
			await run_sync(data.save)

			message = Message(author=connection.user, chat=chat, data=data, type='text')
			await run_sync(message.save)

			for conn in self.chats[chat.title]:
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
		except Exception as e:
			print('Exception during deleting message: ', str(e))

	async def notify_img(self, user, chat, file_id):
		'''
			Function is being called from FileHandler.
			Notifies every user in stated chat about new file
		'''
		try:
			for conn in self.chats[chat.title]:
				template = loader.get_template('main/messages.html')
				message = await run_sync(lambda: Message.objects.get(id=str(file_id)))
				html_img = await run_sync(lambda: template.render({'messages': [message], 'user': conn.user}))
				await conn.socket.send(json.dumps({
					'command': 'notify_img',
					'data': str(html_img)
				}))
		except Exception as e:
			print('Error during notifying img: ', str(e))

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
		except self.RegistrationError as e:
			print('Error during user registration: ', str(e))
		except Exception as e:
			print('Unknown error during handle: ', str(e))
		finally:
			await self._unregister(connection, chat)

	async def get_connection_by_user(self, user, chat_title=None):
		if chat_title:
			for connection in self.chats[chat_title]:
				if connection.user.id == user.id:
					return connection
		else:
			for chat in self.chats:
				for connection in self.chats[chat]:
					if connection.user.id == user.id:
						return connection
		return None

	async def get_chat_by_connection(self, connection):
		for chat in self.chats:
			if connection in self.chats[chat]:
				return await run_sync(lambda: Chat.objects.get(title=chat))
		return None

	def is_user_connected(self, user, chat=None, chat_title=None):
		if chat or chat_title:
			if chat:
				chat_title = chat.title
			for connection in self.chats[chat_title]:
				if connection.user.id == user.id:
					return True

		for chat in self.chats:
			for connection in self.chats[chat]:
				if connection.user.id == user.id:
					return True
		return False

	async def remove_users_from_chat(self, users, chat):
		for user in users:
			await self.remove_user_from_chat(user, chat)

	def remove_chat(self, chat):
		if chat.title in self.chats:
			run_async(self.remove_users_from_chat(list(chat.users.all()), chat))
			self.chats.pop(chat.title)


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

	async def notify(self, chat_title, db_message):
		try:
			chat_id = await run_sync(lambda: Chat.objects.get(title=chat_title).id)

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
		except Exception as e:
			print('Exception during notifying chats: ', str(e))

	async def register(self, websocket):
		msg = await websocket.recv()
		cookies = parse_cookie(msg)

		user = await get_user(cookies.get('sessionid'))
		connection = Connection(user=user, socket=websocket)

		chats = await run_sync(lambda: tuple(Chat.objects.filter(users=user)))
		for chat in chats:
			if not self.chats.get(chat.title):
				self.chats[chat.title] = [connection]
			else:
				self.chats[chat.title].append(connection)

		self.connections.append(connection)
		return connection

	async def unregister(self, connection):
		for chat in self.chats:
			if connection in self.chats[chat]:
				self.chats[chat].remove(connection)
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

			for chat in self.chats:
				db_message = await run_sync(lambda: Message.objects.filter(chat__title=chat).order_by('pk').last())
				await self.notify(chat, db_message)

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

	async def remove_user_from_chat(self, user, chat):
		try:
			self.lock.acquire()
			for connection in self.chats[chat.title]:
				if connection.user.id == user.id:
					self.chats[chat.title].remove(connection)
					await connection.socket.send(json.dumps({
						'command': 'remove_chat',
						'chat_id': chat.id,
					}))
					return True
		finally:
			self.lock.release()
		return False

	async def remove_users_from_chat(self, users, chat):
		for user in users:
			if self.is_user_connected(user):
				await self.remove_user_from_chat(user, chat)

	async def add_user_to_chat(self, user, chat):
		try:
			self.lock.acquire()
			for connection in self.connections:
				if connection.user.id == user.id:
					last_message = await run_sync(lambda: Message.objects.filter(chat__title=chat.title).order_by('id').last())
					template = loader.get_template('main/chat.html')
					data = await run_sync(lambda: str(template.render({
						'chat': chat,
						'data': last_message,
					})))
					await connection.socket.send(json.dumps({
						'command': 'add_chat',
						'data': data
					}))
					if self.chats.get(chat.title):
						self.chats[chat.title].append(connection)
					else:
						self.chats[chat.title] = [connection]

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

	def rename_chat(self, before, now):
		try:
			self.lock.acquire()
			if self.chats.get(before):
				connections = self.chats[before]
				self.chats.pop(before)
				self.chats[now] = connections
		finally:
			self.lock.release()

	def remove_chat(self, chat):
		if chat.title in self.chats:
			run_async(self.remove_users_from_chat(list(chat.users.all()), chat))
			connections = self.chats.pop(chat.title)
			for connection in connections:
				self.connections.remove(connection)


class WebSocketHandler:
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

