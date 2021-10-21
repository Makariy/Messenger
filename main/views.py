from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, \
    FileResponse, HttpResponseBadRequest, JsonResponse
from django.views.generic import View


from django.contrib.auth import get_user, authenticate, login, logout
from django.urls import reverse_lazy
from django.shortcuts import redirect

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from django.views.decorators.csrf import csrf_exempt

from .routine import PageBase

from .db_services import *
from .runtime_services import *
from .messages_service import *


websocket_server = WebSocketHandler()


class Authorization(View):
    def dispatch(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            return redirect(reverse_lazy('messages_page'))
        return super().dispatch(request, *params, **args)

    def post(self, request: HttpRequest, *params, **args):
        if not request.POST.get('username') and not request.POST.get('password'):
            return redirect('login')

        data = {}
        for key in request.POST.keys():
            data[key] = request.POST[key].strip()

        user = authenticate(username=data['username'], password=data['password'])
        if not user:
            return self.get(request, 'Invalid credentials')

        login(request, user)
        return redirect('messages_page')

    def get(self, request: HttpRequest, *params, **args):
        context = {'error': params[0] if not params == () else ''}
        return HttpResponse(render(request, 'main/login.html', context))


class Registration(View):
    def dispatch(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if user and not user.is_anonymous:
            return redirect(reverse_lazy('messages_page'))
        return super().dispatch(request, *params, **args)

    def post(self, request, *params, **args):
        data = {}
        for key in request.POST.keys():
            data[key] = request.POST[key].strip()

        try:
            user = create_user_by_params(username=data['username'], password=data['password'], email=data['email'])
        except ValidationError as e:
            return self.get(request, e.message)

        login(request, user)
        return redirect('messages_page')

    def get(self, request, *params, **args):
        context = {'error': params[0] if not params == () else ''}
        return render(request, 'main/signup.html', context)


@login_required
def request_session_id(request):
    return HttpResponse(request.COOKIES.get('sessionid'))


class MessagesPage(View):
    @method_decorator(login_required)
    def dispatch(self, request, *params, **args):
        args['user'] = get_user(request)
        return super().dispatch(request, *params, **args)

    def get(self, request, *params, **args):
        chat_id = request.session.get('chat_id')
        if not chat_id:
            return redirect('chats_handler')
        try:
            chat = get_chat_by_params(id=int(chat_id))
            if not chat:
                raise ValueError
            if args['user'] not in chat.users.all():
                request.session['chat_id'] = None
                return redirect('chats_handler')
        except ValueError:
            return redirect('chats_handler')
        messages = get_last_messages(chat=chat)
        context = {'messages': messages, 'user': args['user']}
        return render(request, 'main/index.html', context)


@method_decorator(login_required, name='dispatch')
class ChatsHandler(View):
    def get(self, request: HttpRequest, *params, **args):
        action = request.GET.get('action')

        if action == 'exit_chat':
            request.session['chat_id'] = None
            return redirect('messages_page')

        if action == 'exit':
            logout(request)
            request.session['chat_id'] = None
            return redirect('messages_page')

        if action == 'get_chat':
            request.session['chat_id'] = request.GET.get('chat_id')
            return redirect('messages_page')

        if action == 'create_chat':
            return redirect('create_chat')

        if not action:
            user = get_user(request)
            chats = filter_chat_by_params(users__id=user.id)
            last_messages = get_last_chats_messages(chats)

            display = []
            for i in range(len(chats)):
                display.append([chats[i], last_messages[i]])
            context = {'displays': display}
            return render(request, 'main/chats.html', context)

        return HttpResponseBadRequest()


@method_decorator(login_required, name='dispatch')
class ChatsCreator(View):
    @staticmethod
    def get_users_to_invite(request):
        now_user = get_user(request)
        users = list(get_all_users())
        users.remove(now_user)
        return users

    def get(self, request: HttpRequest, *params, **args):
        users = ChatsCreator.get_users_to_invite(request)
        return render(request, 'main/chat_create.html', {'users': users})

    def post(self, request: HttpRequest, *params, **args):
        author = get_user(request)
        title = request.POST.get('title', "").strip()

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
            return JsonResponse({'status': 'fail', 'error': e.message})

        return JsonResponse({'status': 'success'})


@method_decorator(login_required, name='dispatch')
class UserSettings(View):
    def get(self, request: HttpRequest, *params, **args):
        try:
            user = get_user(request)
        except ObjectDoesNotExist:
            return redirect(reverse_lazy('messages_page'))

        return render(request, 'main/user_settings.html', {'user': user})


class FileHandler(View):
    @method_decorator(csrf_exempt)
    @method_decorator(login_required)
    def dispatch(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        if not user or user.is_anonymous:
            return redirect('messages_page')

        try:
            chat = get_chat_by_params(id=int(request.session.get('chat_id')))
        except (ObjectDoesNotExist, ValueError, TypeError):
            return redirect('messages_page')
        if chat not in filter_chat_by_params(users=user):
            return redirect('messages_page')

        args['user'] = user
        args['chat'] = chat
        return super().dispatch(request, *params, **args)

    def post(self, request: HttpRequest, *params, **args):
        file = request.FILES.get('file')
        file_title = request.POST.get('file_title')

        if not file or not file_title:
            return JsonResponse({'status': 'fail'})

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
        return JsonResponse({'status': 'success'})

    def get(self, request: HttpRequest, *params, **args):
        try:
            message = get_message_by_params(id=int(request.GET.get('file_id')))
            if message is None:
                raise ValueError
            return FileResponse(message.data.file)
        except (ValueError, TypeError):
            return HttpResponseBadRequest(request)


class ChatSettings(View):
    @method_decorator(login_required)
    def dispatch(self, request: HttpRequest, *params, **args):
        user = get_user(request)
        chat_id = request.session.get('chat_id')
        try:
            chat = get_chat_by_params(id=int(chat_id))
        except (ObjectDoesNotExist, ValueError):
            chat = None

        if chat:
            if user in chat.users.all():
                args['user'] = user
                args['chat'] = chat
                return super().dispatch(request, *params, **args)

        return redirect('messages_page')

    def get(self, request: HttpRequest, *params, **args):
        action = request.GET.get('action')
        if action == 'delete':
            if args['chat'].admin == args['user']:
                delete_chat(args['chat'])
                request.session['chat_id'] = None
                return redirect('messages_page')

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
            return HttpResponseBadRequest()

        # Get users to add
        users = []
        for user_id in request.POST.getlist('users[]'):
            try:
                user = get_user_by_params(id=int(user_id))
                if user:
                    users.append(user)
            except (ValueError, TypeError):
                pass

        try:
            update_chat(args['chat'], title, users)
        except ValidationError as e:
            return JsonResponse({'status': 'fail', 'error': e.message})

        return JsonResponse({'status': 'success'})
