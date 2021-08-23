import asyncio
import json
import time
from websockets.exceptions import ConnectionClosedOK

from django.http.cookie import parse_cookie
from django.template import loader

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
	user = await run_sync(lambda: User.objects.all().get(id=session.get_decoded().get('_auth_user_id')))
	return user


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
			'del': self.delete,
		}

	async def _register(self, websocket):
		'''
			Adds websocket to monitoring chats and active connections
		'''
		try:
			cookies = parse_cookie(await websocket.recv())

			user = await get_user(cookies['sessionid'])
			chat = await run_sync(lambda: Chat.objects.all().get(title=cookies.get('chat_name')))
			chats = await run_sync(lambda: tuple(Chat.objects.all().filter(users__username=user.username)))

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

	async def unregister(self, user=None, chat=None, connection=None):
		if user and chat:
			connection = await self.get_connection_by_user(user, chat.title)

		if connection:
			await connection.socket.send(json.dumps({
				'command': 'disconnect',
				'code': 'DISCONNECTED'
			}))

	async def _send_message(self, connection, message):
		template = loader.get_template('main/messages.html')
		await connection.socket.send(json.dumps({
			'command': 'send_mes',
			'data': str(template.render({'messages': [message], 'user': connection.user})),
		}))

	async def send_message(self, connection, chat, text):
		data = MessageData(text=text)
		await run_sync(data.save)

		message = Message(author=connection.user, chat=chat, data=data, type='text')
		await run_sync(message.save)

		for conn in self.chats[chat.title]:
			await self._send_message(conn, message)

	async def delete(self, connection, chat, chat_id):
		'''
			Deletes message from chat with stated chat_id
		'''
		try:
			message = await run_sync(lambda: Message.objects.all().get(id=int(chat_id)))
			if await run_sync(lambda: connection.user == message.author):
				await run_sync(message.delete)
				for _connection in self.chats[chat.title]:
					await _connection.socket.send(json.dumps({
						'command': 'del',
						'data': chat_id,
					}))
		except:
			pass

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
					await func(connection, chat, message['data'])
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
				return await run_sync(lambda: Chat.objects.all().get(title=chat))
		return None

	async def notify_img(self, user, chat, file_id):
		'''
			Function is being called from FileHandler.
			Notifies every user in stated chat about new file
		'''
		for conn in self.chats[chat.title]:
			template = loader.get_template('main/messages.html')
			message = await run_sync(lambda: Message.objects.all().get(id=str(file_id)))
			html_img = await run_sync(lambda: template.render({'messages': [message], 'user': conn.user}))
			await conn.socket.send(json.dumps({
				'command': 'notify_img',
				'data': str(html_img)
			}))


class ChatServer:
	chats = {}
	connections = []
	is_monitoring = False

	def is_monitoring_empty(self):
		for chat in self.chats:
			if not len(self.chats[chat]) == 0:
				return False
		return True

	async def notify(self, chat):
		try:
			chat_id = await run_sync(lambda: Chat.objects.all().get(title=chat).pk)
			db_message = await run_sync(lambda: Message.objects.all().filter(chat__title=chat).order_by('pk').last())

			if db_message:
				author_name = await run_sync(lambda: db_message.author.username)
				if db_message.type == 'text':
					message = await run_sync(lambda: db_message.data.text)
				else:
					message = 'Photo'
				data = str(author_name) + ': ' + str(message)
			else:
				data = 'There are no messages right now. You can be first to write something!'
			for connection in self.chats[chat]:
				await connection.socket.send(json.dumps({
					'chat_id': str(chat_id),
					'data': data,
				}))
		except:
			pass

	async def register(self, websocket):
		cookies = parse_cookie(await websocket.recv())

		user = await get_user(cookies.get('sessionid'))
		chats = await run_sync(lambda: tuple(Chat.objects.all().filter(users=user)))
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

