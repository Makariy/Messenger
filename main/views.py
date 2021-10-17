from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, FileResponse

from django.contrib.auth import get_user, authenticate, login, logout
from django.urls import reverse_lazy
from django.shortcuts import redirect

from django.views.decorators.csrf import csrf_exempt

from .routine import PageBase

from .db_services import *
from .messages_service import *


websocket_server = WebSocketHandler()


class Authorization(PageBase):
    def handle(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            return redirect(reverse_lazy('messages_page'))
        return super().handle(request, *params, **args)

    def post(self, request: HttpRequest, *params, **args):
        if not request.POST.get('username') and request.POST.get('password'):
            return self.redirect('login')

        data = {}
        for key in request.POST.keys():
            data[key] = request.POST[key].strip()

        user = authenticate(username=data['username'], password=data['password'])
        if not user:
            return self.get(request, 'Invalid credentials')

        login(request, user)
        return self.redirect('messages_page')

    def get(self, request: HttpRequest, *params, **args):
        context = {'error': params[0] if not params == () else ''}
        return HttpResponse(render(request, 'main/login.html', context))


class Registration(PageBase):
    def handle(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            return redirect(reverse_lazy('messages_page'))
        return super().handle(request, *params, **args)

    def post(self, request, *params, **args):
        data = {}
        for key in request.POST.keys():
            data[key] = request.POST[key].strip()

        try:
            user = create_user_by_params(username=data['username'], password=data['password'], email=data['email'])
        except ValidationError as e:
            return self.get(request, e.message)

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
        chat_id = request.COOKIES.get('chat_id')
        if not chat_id:
            return self.redirect('chats_handler')
        try:
            chat = get_chat_by_params(id=int(chat_id))
            if not chat:
                raise ValueError
            if args['user'] not in chat.users.all():
                return self.redirect('chats_handler', {'chat_id': None})
        except ValueError:
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
            return self.redirect('messages_page', {'chat_id': None})

        if action == 'exit':
            logout(request)
            return self.redirect('messages_page', {'chat_id': None})

        if action == 'get_chat':
            return self.redirect('messages_page', {'chat_id': request.GET.get('chat_id')})

        if action == 'create_chat':
            return self.redirect('create_chat')

        if not action:
            user = get_user(request)
            chats = filter_chat_by_params(users__id=user.id)
            last_messages = get_last_chats_messages(chats)

            display = []
            for i in range(len(chats)):
                display.append([chats[i], last_messages[i]])
            context = {'displays': display}
            return render(request, 'main/chats.html', context)

        return HttpResponse('')


class ChatsCreator(PageBase):
    @staticmethod
    def get_users_to_invite(request):
        now_user = get_user(request)
        users = list(get_all_users())
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
        title = request.POST.get('title', "").strip()

        if title:
            users = []
            users_id = request.POST.getlist('users[]')
            for user_id in users_id:
                try:
                    users.append(get_user_by_params(id=int(user_id)))
                except ValueError:
                    pass
            try:
                create_chat_by_params(title=title, admin=author, users=users)
            except ValidationError as e:
                return HttpResponse(e.message)

            return HttpResponse()

        return HttpResponse()


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
            chat = get_chat_by_params(id=int(request.COOKIES.get('chat_id')))
        except (ObjectDoesNotExist, ValueError):
            return self.redirect('messages_page')
        if not user or user.is_anonymous or (chat not in filter_chat_by_params(users=user)):
            return self.redirect('messages_page')
        args['user'] = user
        args['chat'] = chat
        return super().handle(request, *params, **args)

    def post(self, request: HttpRequest, *params, **args):
        file = request.FILES.get('file')
        file_title = request.POST.get('file_title')

        md = MessageData()
        md.file.save(file_title, file)

        message = None
        for form in ('.jpg', 'jpeg', '.png', '.tiff', '.heic'):
            if file_title.endswith(form):
                message = Message(author=args['user'], chat=args['chat'], data=md, type='image')
        for form in ('.mp4', '.webm', '.avi', '.mov', '.ogg', '.ogv'):
            if file_title.endswith(form):
                message = Message(author=args['user'], chat=args['chat'], data=md, type='video')
        if not message:
            message = Message(author=args['user'], chat=args['chat'], data=md, type='file')

        message.save()
        run_async(websocket_server.get_messenger().notify_file(args['user'], args['chat'], message.id))
        return HttpResponse('')

    def get(self, request: HttpRequest, *params, **args):
        file = Message.objects.get(id=int(request.GET.get('file_id'))).data.file
        return FileResponse(file.file)


class ChatSettings(PageBase):
    def handle(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        chat_id = request.COOKIES.get('chat_id')
        try:
            chat = get_chat_by_params(id=int(chat_id))
        except (ObjectDoesNotExist, ValueError):
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
                delete_chat(args['chat'])
                return self.redirect('messages_page', {'chat_id': None})

        users = ChatsCreator.get_users_to_invite(request)
        users_to_invite = ''
        for user in args['chat'].users.all():
            if not user.id == args['user'].id:
                users_to_invite += str(user.id) + ', '
        context = {'users': users, 'users_to_invite': users_to_invite, 'chat': args['chat'], 'user': args['user']}
        return render(request, 'main/chat_settings.html', context)

    def post(self, request: HttpRequest, *params, **args):
        title = request.POST.get('title', "").strip()
        if not title:
            return HttpResponse('')

        # Get users to add
        users = []
        for user_id in request.POST.getlist('users[]'):
            try:
                user = get_user_by_params(id=int(user_id))
                if user:
                    users.append(user)
            except ValueError:
                pass

        try:
            update_chat(args['chat'], title, users)
        except ValidationError as e:
            return HttpResponse(e.message)

        return HttpResponse('')
