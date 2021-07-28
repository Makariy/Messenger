import asyncio
import websockets

from django.http.cookie import parse_cookie
from django.template import loader

from ..models import User, Chat, Message
from ..routine import StringHasher


class Socket:
	def __init__(self, user, socket):
		self.user = user
		self.socket = socket

	user = None
	socket = None




async def get_user(cookies):
	loop = asyncio.get_event_loop()
	db_user = await loop.run_in_executor(None, lambda: User.objects.all().get(name=cookies['user_name']))

	if StringHasher.get_hash(db_user.password) == cookies.get('user_password'):
		return db_user


class MessageServer():
	chats = {}
	sockets = {}

	async def register(self, websocket):
		cookies = parse_cookie(await websocket.recv())

		user = await get_user(cookies)
		chat = await asyncio.get_event_loop().run_in_executor(None, lambda: Chat.objects.all().get(title=cookies.get('chat_name')))

		chats = await asyncio.get_event_loop().run_in_executor(None, lambda: tuple(Chat.objects.all().filter(users__name=user.name)))

		# Add user to correct chat query
		if chat in chats:
			socket = Socket(user=user, socket=websocket)
			if not self.chats.get(chat.title):
				self.chats[chat.title] = [socket,]
			else:
				self.chats[chat.title].append( socket )

			self.sockets[websocket] = (socket, chat)
			return True

		return False

	async def unregister(self, websocket):
		socket, chat = self.sockets[websocket]
		self.chats[chat.title].remove(socket)
		await websocket.close()

	async def send_message(self, socket, message):
		template = loader.get_template('main/messages.html')
		print(str(template.render({'messages': [message]})))
		await socket.socket.send(str(template.render({'messages': [message]})))

	async def handle(self, websocket, path):
		try:
			if not await self.register(websocket):
				raise Exception()
			print(self.chats)
			sock, chat = self.sockets[websocket]
			while True:
				text = await websocket.recv()
				for socket in self.chats[chat.title]:
					message = Message(author=sock.user, chat=chat, message=text)
					await asyncio.get_event_loop().run_in_executor(None, message.save)
					await self.send_message(socket, message)

		except:
			pass
		finally:
			await self.unregister(websocket)



