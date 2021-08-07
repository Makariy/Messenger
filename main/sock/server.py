import asyncio
import websockets

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
	chats = {}
	connections = {}

	def __init__(self):
		self.commands = {
			'send_mes': self.send_message,
			'del': self.delete,
			'notify_img': self.notify_img,
		}

	async def register(self, websocket):
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

			self.connections[websocket] = (connection, chat)
			return True

		return False

	async def unregister(self, websocket):
		if self.connections.get(websocket):
			connection, chat = self.connections[websocket]
			self.chats[chat.title].remove(connection)
		await websocket.close()

	async def _send_message(self, connection, message):
		template = loader.get_template('main/messages.html')
		await connection.socket.send('send_mes')
		await connection.socket.send(str(template.render({'messages': [message], 'user': connection.user})))

	async def send_message(self, sock, chat, text):
		data = MessageData(text=text)
		await run_sync(data.save)

		message = Message(author=sock.user, chat=chat, data=data, type='text')
		await run_sync(message.save)

		for connection in self.chats[chat.title]:
			await self._send_message(connection, message)

	async def delete(self, connection, chat, text):
		try:
			message = await run_sync(lambda: Message.objects.all().get(id=int(text)))
			if await run_sync(lambda: connection.user == message.author):
				await run_sync(lambda: message.delete())
				for _connection in self.chats[chat.title]:
					await _connection.socket.send('del')
					await _connection.socket.send(text)
		except:
			pass

	async def notify_img(self, connection, chat, id):
		for conn in self.chats[chat.title]:
			await conn.socket.send('notify_img')
			template = loader.get_template('main/messages.html')
			message = await run_sync(lambda: Message.objects.all().get(id=str(id)))
			html_img = await run_sync(lambda: template.render({'messages': [message], 'user': connection.user}))
			await conn.socket.send(str(html_img))

	async def handle(self, websocket, path):
		try:
			if not await self.register(websocket):
				raise Exception()
			connection, chat = self.connections[websocket]
			while True:
				command = await websocket.recv()
				func = self.commands.get(command)
				if func:
					await func(connection, chat, await websocket.recv())
		except:
			pass
		finally:
			await self.unregister(websocket)


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
			db_message = await run_sync(lambda: Message.objects.all().filter(chat__title=chat).order_by('pk').last())
			author_name = await run_sync(lambda: db_message.author.username)
			if db_message.type == 'text':
				message = await run_sync(lambda: db_message.data.text)
			else:
				message = 'Photo'
			chat_id = await run_sync(lambda: Chat.objects.all().get(title=chat).pk)
			for connection in self.chats[chat]:
				await connection.socket.send(str(chat_id))
				await connection.socket.send(str(author_name) + ': ' + str(message))
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
				return
			for chat in self.chats:
				await self.notify(chat)
			await asyncio.sleep(1)

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
		except:
			pass
		finally:
			if connection is not None:
				await self.unregister(connection)

