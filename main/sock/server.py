import asyncio
import websockets

from django.http.cookie import parse_cookie
from django.template import loader

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from ..models import Chat, Message
from ..routine import StringHasher


class Connection:
	def __init__(self, user, socket):
		self.user = user
		self.socket = socket

	user = None
	socket = None

async def run_sync(func):
	return await asyncio.get_event_loop().run_in_executor(None, func)


class MessageServer():
	chats = {}
	connections = {}

	def __init__(self):
		self.commands = {
			'send': self.send,
			'del': self.delete,
		}

	def _get_user(self, session_id):
		session = Session.objects.get(session_key=session_id)
		return User.objects.all().get(id=session.get_decoded().get('_auth_user_id'))

	async def get_user(self, session_id):
		loop = asyncio.get_event_loop()
		return await run_sync(lambda: self._get_user(session_id))

	async def register(self, websocket):
		cookies = parse_cookie(await websocket.recv())

		user = await self.get_user(cookies['sessionid'])
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
		await connection.socket.send('send')
		await connection.socket.send(str(template.render({'messages': [message], 'user': connection.user})))

	async def send(self, sock, chat, text):
		for socket in self.chats[chat.title]:
			message = Message(author=sock.user, chat=chat, message=text)
			await run_sync(message.save)
			await self._send_message(socket, message)

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

	async def handle(self, websocket, path):
		try:
			if not await self.register(websocket):
				raise Exception()
			sock, chat = self.connections[websocket]
			while True:
				command = await websocket.recv()
				func = self.commands.get(command)
				if func:
					await func(sock, chat, await websocket.recv())

		except:
			pass
		finally:
			await self.unregister(websocket)



