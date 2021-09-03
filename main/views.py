from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, FileResponse

from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.core.exceptions import ObjectDoesNotExist

from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.models import User
from django.contrib.auth import get_user, authenticate, login, logout

from .models import Message
from .models import MessageData
from .models import Chat

from .routine import PageBase

from .sock.server import run_async
from .sock.server import get_last_messages
from .sock.server import WebSocketHandler
from .sock.server import WebSocketAdmin


websocket_server = WebSocketHandler()
websocket_server.start()

websocket_admin = WebSocketAdmin()


class Authorization(PageBase):
    def _check_user(self, data):
        try:
            user = User.objects.get(username=data.get('username'))
            if not user.check_password(data.get('password')):
                return 'Incorrect password'
            else:
                return ''
        except:
            return 'User with this name doesn\'t exist'

    def handle(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            return redirect(reverse_lazy('messages_page'))
        return super().handle(request, *params, **args)

    def post(self, request: HttpRequest, *params, **args):
        user = authenticate(username=request.POST['username'], password=request.POST['password'])
        error = self._check_user(request.POST)
        if not error == '' or not user:
            return self.get(request, error)

        login(request, user)
        return self.redirect('messages_page')

    def get(self, request: HttpRequest, *params, **args):
        context = {'error': params[0] if not params == () else ''}
        return HttpResponse(render(request, 'main/login.html', context))


class Registration(PageBase):
    def check_user(self, user):
        if (user['username'] == '') or (user['username'][0].isdigit()) or (len(user['username']) < 2):
            return "Your name is too short or starts with a digit"
        if (len(user['password']) < 6) or (not user['password'].lower().find(user['username'].lower()) == -1):
            return "Your password is too short or contains your name"
        if User.objects.filter(username=user['username']).count() > 0:
            return "This name is already used"
        if User.objects.filter(email=user['email']).count() > 0:
            return "This mail is already used"
        return ''

    def handle(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            return redirect(reverse_lazy('messages_page'))
        return super().handle(request, *params, **args)

    def post(self, request, *params, **args):
        data = request.POST
        error = self.check_user(request.POST)
        if not error == '':
            return self.get(request, error)

        user = User.objects.create_user(username=data['username'], password=data['password'], email=data['email'])
        login(request, user)
        return self.redirect('messages_page')

    def get(self, request, *params, **args):
        context = {'error': params[0] if not params == () else ''}
        return render(request, 'main/signup.html', context)


def request_session_id(request):
    return HttpResponse(request.COOKIES.get('sessionid'))


class MessagesPage(PageBase):
    def handle(self, request, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            args['user'] = user
            return super().handle(request, *params, **args)

        return self.redirect('login')

    def get(self, request, *params, **args):
        chat_title = request.COOKIES.get('chat_name')
        if not chat_title:
            return self.redirect('chats_handler')
        try:
            chat = Chat.objects.get(title=chat_title)
            if args['user'] not in chat.users.all():
                return self.redirect('chats_handler', {'chat_name': None})
        except ObjectDoesNotExist:
            return self.redirect('chats_handler')
        messages = get_last_messages(chat=chat)
        context = {'messages': messages, 'user': args['user']}
        return render(request, 'main/index.html', context)


class ChatsHandler(PageBase):
    def handle(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            return super().handle(request, *params, **args)
        return self.redirect('messages_page')

    def get(self, request: HttpRequest, *params, **args):
        action = request.GET.get('action')

        if action == 'exit_chat':
            return self.redirect('messages_page', {'chat_name': None})

        if action == 'exit':
            logout(request)
            return self.redirect('messages_page', {'chat_name': None})

        if action == 'get_chat':
            return self.redirect('messages_page', {'chat_name': request.GET.get('chat_name')})

        if action == 'create_chat':
            return self.redirect('create_chat')

        if not action:
            user = get_user(request)
            chats = Chat.objects.filter(users__username=user.username)
            last_messages = [Message.objects.filter(chat=chat).order_by('pk').last() for chat in chats]

            display = []
            for i in range(len(chats)):
                display.append([chats[i], last_messages[i]])
            context = {'displays': display}
            return render(request, 'main/chats.html', context)

        return HttpResponse('')


class ChatsCreator(PageBase):
    @staticmethod
    def check_chat(request):
        data = request.POST
        if len(Chat.objects.filter(title=data['title'])) > 0:
            return 'Chat with this name already exist'
        if len(data['title']) < 2:
            return 'Chat title must be longer than 2'
        for ch in data['title']:
            if not 65 <= ord(ch) <= 122:
                return 'Chat title must be in english'

        return None

    @staticmethod
    def get_users_to_invite(request):
        now_user = get_user(request)
        users = list(User.objects.all())
        users.remove(now_user)
        return users

    def handle(self, request: HttpRequest, *params, **args):
        if not get_user(request).is_anonymous:
            return super().handle(request, *params, **args)
        return redirect(reverse_lazy('messages_page'))

    def get(self, request: HttpRequest, *params, **args):
        users = ChatsCreator.get_users_to_invite(request)
        return render(request, 'main/chat_create.html', {'users': users})

    def post(self, request: HttpRequest, *params, **args):
        author = get_user(request)

        error = ChatsCreator.check_chat(request)
        if not error:
            chat = Chat()
            chat.title = request.POST.get('title')
            chat.admin = author
            chat.save()
            chat.users.add(author)
            users_id = request.POST.getlist('users[]')
            for user_id in users_id:
                try:
                    user = User.objects.get(id=int(user_id))
                    chat.users.add(user)

                    if websocket_server.get_chat().is_user_connected(user):
                        run_async(websocket_server.get_chat().add_user_to_chat(user, chat))

                except ObjectDoesNotExist:
                    pass
                except ValueError:
                    pass
            return HttpResponse()

        return HttpResponse(error)


class UserSettings(PageBase):
    def get(self, request: HttpRequest, *params, **args):
        try:
            user = get_user(request)
        except ObjectDoesNotExist:
            return redirect(reverse_lazy('messages_page'))

        return render(request, 'main/user_settings.html', {'user': user})


class FileHandler(PageBase):
    @csrf_exempt
    def handle(self, request: HttpRequest, *params, **args):
        try:
            user = get_user(request)
            chat = Chat.objects.get(title=request.COOKIES.get('chat_name'))
        except ObjectDoesNotExist:
            return self.redirect('messages_page')
        if (not user) or (user.is_anonymous) or (chat not in Chat.objects.filter(users=user)):
            return self.redirect('messages_page')
        args['user'] = user
        args['chat'] = chat
        return super().handle(request, *params, **args)

    def post(self, request: HttpRequest, *params, **args):
        file = request.FILES.get('file')
        file_title = request.POST.get('file_title')

        md = MessageData()
        md.image.save(file_title, file)
        message = Message(author=args['user'], chat=args['chat'], data=md, type='image')
        message.save()
        run_async(websocket_server.get_messenger().notify_img(args['user'], args['chat'], message.id))
        return HttpResponse('')

    def get(self, request: HttpRequest, *params, **args):
        image = Message.objects.get(id=int(request.GET.get('file_id'))).data.image
        return FileResponse(image.file)


class ChatSettings(PageBase):
    def handle(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        chat_title = request.COOKIES.get('chat_name')
        try:
            chat = Chat.objects.get(title=chat_title)
        except ObjectDoesNotExist:
            chat = None

        if user and not user.is_anonymous and chat:
            if user in chat.users.all():
                args['user'] = user
                args['chat'] = chat
                return super().handle(request, *params, **args)

        return self.redirect('messages_page')

    def get(self, request: HttpRequest, *params, **args):
        action = request.GET.get('action')
        if action == 'delete':
            if args['chat'].admin == args['user']:
                websocket_server.get_chat().remove_chat(args['chat'])
                websocket_server.get_messenger().remove_chat(args['chat'])
                args['chat'].delete()

                return self.redirect('messages_page', {'chat_name': None})

        users = ChatsCreator.get_users_to_invite(request)
        users_to_invite = ''
        for user in args['chat'].users.all():
            if not user.id == args['user'].id:
                users_to_invite += str(user.id) + ', '
        context = {'users': users, 'users_to_invite': users_to_invite, 'chat': args['chat'], 'user': args['user']}
        return render(request, 'main/chat_settings.html', context)

    def post(self, request: HttpRequest, *params, **args):
        # Get users to add
        users_ids = []
        for user_id in request.POST.getlist('users[]'):
            try:
                users_ids.append(int(user_id))
            except ValueError:
                pass

        chat_server = websocket_server.get_chat()
        messenger_server = websocket_server.get_messenger()

        # Rename chat
        chat_server.rename_chat(args['chat'].title, request.POST.get('title'))
        args['chat'].title = request.POST.get('title')

        # Add users to chat
        if users_ids:
            for user_id in users_ids:
                try:
                    user = User.objects.get(id=user_id)
                    if user not in args['chat'].users.all():
                        args['chat'].users.add(user)
                        # If user is connected to chat_server, then notify him about new chat
                        if chat_server.is_user_connected(user):
                            run_async(chat_server.add_user_to_chat(user, args['chat']))

                except ObjectDoesNotExist:
                    pass

        # Remove users
        for user in args['chat'].users.all():
            try:
                if (user.id not in users_ids) and (not user.id == args['user'].id):
                    args['chat'].users.remove(user)
                    # If user is connected to messenger_server, then stop notifying him
                    if messenger_server.is_user_connected(user):
                        run_async(messenger_server.remove_user_from_chat(user, args['chat']))
                    # If user is connected to chat_server, then stop notifying him
                    if chat_server.is_user_connected(user):
                        run_async(chat_server.remove_user_from_chat(user, args['chat']))

            except ObjectDoesNotExist:
                pass

        args['chat'].save()
        return self.redirect('messages_page', {'chat_name': args['chat'].title})
