import asyncio
import websockets
import threading
from .sock.server import MessageServer

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.core.exceptions import ObjectDoesNotExist

from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.models import User
from django.contrib.auth import get_user, authenticate, login, logout
from django.contrib.auth.hashers import make_password

from .models import Message
from .models import Chat

from .routine import StringHasher
from .routine import PageBase




class Authorization(PageBase):
    def _check_user(self, data):
        try:
            user = User.objects.all().get(username=data.get('username'))
            if not user.check_password(data.get('password')):
                return 'Password incorrect'
            else:
                return ''
        except:
            return 'User with this name doesn\'t exist'

    def handle(self, request: HttpRequest, *params, **args):
        if not get_user(request).is_anonymous:
            return redirect(reverse_lazy('main'))
        return super().handle(request, *params, **args)

    def post(self, request: HttpRequest, *params, **args):
        user = authenticate(username=request.POST['username'], password=request.POST['password'])
        error = self._check_user(request.POST)
        if not error == '' or not user:
            return self.get(request, error)

        login(request, user)
        return self.redirect('main')

    def get(self, request: HttpRequest, *params, **args):
        context = {'error': params[0] if not params == () else ''}
        return HttpResponse(render(request, 'main/login.html', context))


class Registration(PageBase):
    def check_user(self, user):
        if (user['username'] == '') or (user['username'][0].isdigit()) or (len(user['username']) < 2):
            return "Your name is too short or starts with a digit"
        if (len(user['password']) < 6) or (not user['password'].lower().find(user['username'].lower()) == -1):
            return "Your password is too short or contains your name"
        if User.objects.all().filter(username=user['username']).count() > 0:
            return "This name is already used"
        if User.objects.all().filter(email=user['email']).count() > 0:
            return "This mail is already used"
        return ''

    def handle(self, request: HttpRequest, *params, **args):
        if not get_user(request).is_anonymous:
            return redirect(reverse_lazy('main'))
        return super().handle(request, *params, **args)

    def post(self, request, *params, **args):
        data = request.POST
        error = self.check_user(request.POST)
        if not error == '':
            return self.get(request, error)

        print(request.POST)
        user = User.objects.create_user(username=data['username'], password=data['password'], email=data['email'])
        login(request, user)
        return self.redirect('main')

    def get(self, request, *params, **args):
        context = {'error': params[0] if not params == () else ''}
        return render(request, 'main/signup.html', context)


class MessagesHandler(PageBase):
    @csrf_exempt
    def handle(self, request, *params, **args):
        if not get_user(request).is_anonymous:
            return super().handle(request, *params, **args)
        else:
            return redirect(reverse_lazy('main'))

    # User check is in handle function
    def get(self, request, *params, **args):
        try:
            message_id = request.GET.get('message_id')
            message_id = int(message_id)
            user = get_user(request)
            chat = Chat.objects.all().get(title=request.COOKIES.get('chat_name'))
            if not chat.users.get(username=user.username) == user:
                return HttpResponse('')
        except:
            return HttpResponse('')

        if message_id == -1:
            return render(request, 'main/messages.html', {'messages': Message.objects.all().filter(chat=chat).order_by('pk')})

        new_messages = []
        for message in Message.objects.all().filter(chat=chat).order_by('pk'):
            if message.pk > message_id:
                new_messages.append(message)
        return render(request, 'main/messages.html', {'messages': new_messages, 'user': user})


def request_session_id(request):
    return HttpResponse(request.COOKIES.get('sessionid'))

def start_socket(host):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    server = MessageServer()

    start_server = websockets.serve(server.handle, host, 8001)
    loop.run_until_complete(start_server)
    loop.run_forever()


class MainPage(PageBase):
    websocket_thread = threading.Thread(target=lambda:print('You must restore this thread to create WebSocket thread'))

    def handle(self, request, *params, **args):
        if not self.websocket_thread.is_alive():
            self.websocket_thread = threading.Thread(target=start_socket, args=(request.get_host().split(':')[0],))
            self.websocket_thread.start()

        if not get_user(request).is_anonymous:
            return super().handle(request, *params, **args)
        return self.redirect('login')

    def get(self, request, *params, **args):
        chat_title = request.COOKIES.get('chat_name')
        if chat_title is None:
            return self.redirect('chats_handler')

        try:
            chat = Chat.objects.all().get(title=chat_title)
        except ObjectDoesNotExist:
            return self.redirect('chats_handler')
        messages = Message.objects.all().filter(chat=chat)
        context = {'messages': messages}
        return render(request, 'main/index.html', context)


class ChatsHandler(PageBase):
    def handle(self, request: HttpRequest, *params, **args):
        if not get_user(request).is_anonymous:
            return super().handle(request, *params, **args)
        return redirect(reverse_lazy('main'))

    def get(self, request: HttpRequest, *params, **args):
        action = request.GET.get('action')

        if action == 'exit_chat':
            return self.redirect('main', {'chat_name': None})
        if action == 'exit':
            logout(request)
            return self.redirect('main')

        if action == 'get_chat':
            chat_redirect = request.GET.get('chat_name')
            return self.redirect('main', {'chat_name': chat_redirect})

        if action == 'create_chat':
            return self.redirect('create_chat')

        if not action:
            user = get_user(request)
            chats = Chat.objects.filter(users__username=user.username)
            last_messages = [Message.objects.all().filter(chat=chat).order_by('pk').last() for chat in chats]

            display = []
            for i in range(len(chats)):
                display.append([chats[i], last_messages[i]])
            context = {'displays': display}
            return render(request, 'main/chats.html', context)

        if action == 'exit':
            return self.redirect('chats_handler', {'chat_name': None})

        return HttpResponse('')


class ChatsCreator(PageBase):
    @staticmethod
    def check_chat(request):
        return True

    def get_users(self, request):
        now_user = get_user(request)
        users = list(User.objects.all())
        users.remove(now_user)
        return users

    def handle(self, request: HttpRequest, *params, **args):
        if not get_user(request).is_anonymous:
            return super().handle(request, *params, **args)
        return redirect(reverse_lazy('main'))

    def get(self, request: HttpRequest, *params, **args):
        users = self.get_users(request)
        return render(request, 'main/chat_create.html', {'users': users})

    def post(self, request: HttpRequest, *params, **args):
        if ChatsCreator.check_chat(request):
            chat = Chat()
            chat.title = request.POST.get('title')
            chat.save()
            chat.users.add(get_user(request))
            users_id = request.POST.getlist('users')
            for id in users_id:
                try:
                    chat.users.add(User.objects.all().get(pk=int(id)))
                except ObjectDoesNotExist:
                    pass
                except ValueError:
                    pass

        return self.redirect('chats_handler')


class UserSettings(PageBase):
    def get(self, request: HttpRequest, *params, **args):
        try:
            user = get_user(request)
        except ObjectDoesNotExist:
            return redirect(reverse_lazy('main'))

        return render(request, 'main/user_settings.html', {'user': user})
