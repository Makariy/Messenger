import datetime, json
import os

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

from django.views.generic import edit
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.core.exceptions import ObjectDoesNotExist

from django.views.decorators.csrf import csrf_exempt

from .models import Message
from .models import User
from .models import Chat

from .forms import UserForm

from .routine import StringHasher
from .routine import PageBase


"""
    COOKIES are:
    'user_name'
    'user_password' (hashed)
    'chat_name'
"""




class Authorization(PageBase):
    @staticmethod
    def check_user(request):
        '''
        Checks the request passed as a parameter and returns True if he exists and has the same password
        or returns False if not
        '''
        if request.COOKIES.get('user_name') and request.COOKIES.get('user_password'):
            try:
                db_user = User.objects.all().get(name=request.COOKIES.get('user_name'))
                if request.COOKIES.get('user_password') == StringHasher.get_hash(db_user.password):
                   return True

            except ObjectDoesNotExist:
                pass

        return False

    @staticmethod
    def get_user(request):
        if request.COOKIES.get('user_name') and request.COOKIES.get('user_password'):
            try:
                db_user = User.objects.all().get(name=request.COOKIES.get('user_name'))
                if request.COOKIES.get('user_password') == StringHasher.get_hash(db_user.password):
                    return db_user
            except ObjectDoesNotExist:
                raise
        raise ObjectDoesNotExist()

    def __check_user(self, user, db_user):
        if not db_user:
            return "User with this name doesn't exist"
        if not db_user[0].password == user['password']:
            return "Incorrect password"
        return ''

    def post(self, request: HttpRequest, *params, **args):
        user = UserForm(request.POST)
        db_user = User.objects.all().filter(name=user.data['name'])
        error = self.__check_user(user.data, db_user)
        if not error == '':
            return self.get(request, error)

        ret = redirect(reverse_lazy('main'))
        self.set_cookies(ret, {'user_name': user.data['name'], 'user_password': StringHasher.get_hash(db_user[0].password),
                               'chat': None})
        return ret

    def get(self, request: HttpRequest, *params, **args):
        context = {'form': UserForm}
        if not params == ():
            context['error'] = params[0]
        return HttpResponse(render(request, 'main/login.html', context))


class Registration(PageBase):
    def check_user(self, user):
        if (user['name'] == '') or (user['name'][0].isdigit()) or (len(user['name']) < 2):
            return "Your name is too short or starts with a digit"
        if (len(user['password']) < 6) or (not user['password'].lower().find(user['name'].lower()) == -1):
            return "Your password is too short or contains your name"
        if User.objects.all().filter(name=user['name']).count() > 0:
            return "This name is already used"
        if User.objects.all().filter(mail=user['mail']).count() > 0:
            return "This mail is already used"
        return ''

    def post(self, request, *params, **args):
        post = UserForm(request.POST)
        error = self.check_user(post.data)
        if not error == '' and post.is_valid():
            return self.get(request, error)
        print(post.data['name'], post.data['password'], post.data['mail'])
        user = post.save()
        user.save()
        ret = redirect(reverse_lazy('main'))
        self.set_cookies(ret, {'user_name': user.name, 'user_password': StringHasher.get_hash(user.password)})
        return ret

    def get(self, request, *params, **args):
        context = {'form': UserForm}
        if not params == ():
            context['error'] = params[0]
        return render(request, 'main/signup.html', context)


class MessagesHandler(PageBase):
    @csrf_exempt
    def handle(self, request, *params, **args):
        if Authorization.check_user(request):
            if request.method == 'POST':
                return self.post(request, *params, **args)
            else:
                return self.get(request, *params, **args)
        else:
            return HttpResponse("Don't try to hack me bitch")

    # User check is in handle function
    def get(self, request, *params, **args):
        try:
            message_id = request.GET.get('message_id')
            message_id = int(message_id)
            if message_id == -2:
                Message.objects.all().delete()
        except:
            return self.redirect('main')

        try:
            chat = Chat.objects.all().get(title=request.COOKIES.get('chat_name'))
        except ObjectDoesNotExist:
            return self.redirect('main')

        if message_id == -1:
            return render(request, 'main/messages.html', {'messages': Message.objects.all().filter(chat=chat)})
        new_messages = []
        for message in Message.objects.all().filter(chat=chat):
            if message.pk > message_id:
                new_messages.append(message)
        return render(request, 'main/messages.html', {'messages': new_messages})

    # User check is in handle function
    def post(self, request, *params, **args):
        text = request.POST.get('message')
        if text:
            author = User.objects.all().get(name=request.COOKIES.get('user_name'))
            chat = Chat.objects.all().get(title=request.COOKIES.get('chat_name'))
            message = Message(author=author, chat=chat, message=text)
            message.save()

        return HttpResponse('')


class MainPage(PageBase):
    def handle(self, request, *params, **args):
        if Authorization.check_user(request):
            return super().handle(request, *params, **args)
        return self.redirect('login')

    def get(self, request, *params, **args):
        chat_title = request.COOKIES.get('chat_name')
        if chat_title is None:
            return self.redirect('chats_handler')

        try:
            chat = Chat.objects.all().get(title=request.COOKIES.get('chat_name'))
        except ObjectDoesNotExist:
            return self.redirect('chats_handler')
        messages = Message.objects.all().filter(chat=chat)
        context = {'messages': messages}
        return render(request, 'main/index.html', context)

    def post(self, request, *params, **args):
        return self.redirect('main', {'user_name': None, 'user_password': None, 'chat_name': None})


class ChatsHandler(PageBase):
    def handle(self, request: HttpRequest, *params, **args):
        if Authorization.check_user(request):
            return super().handle(request, *params, **args)
        return redirect(reverse_lazy('main'))

    def post(self, request: HttpRequest, *params, **args):
        return self.redirect('main', {'user_name': None, 'user_password': None})

    def get(self, request: HttpRequest, *params, **args):
        action = request.GET.get('action')

        if action == 'exit_chat':
            return self.redirect('main', {'chat_name': None})
        if action == 'exit':
            return self.redirect('main', {'user_name': None, 'user_password': None, 'chat_name': None})

        if action == 'get_chat':
            chat_redirect = request.GET.get('chat_name')
            return self.redirect('main', {'chat_name': chat_redirect})

        if action == 'create_chat':
            return self.redirect('create_chat')

        if not action:
            user = Authorization.get_user(request)
            chats = Chat.objects.filter(users__name=user.name)
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
        users = []
        now_user = Authorization.get_user(request)
        for user in User.objects.all():
            if not now_user == user:
                users.append(user)
        return users

    def get(self, request: HttpRequest, *params, **args):
        users = self.get_users(request)
        return render(request, 'main/chat_create.html', {'users': users})

    def post(self, request: HttpRequest, *params, **args):
        print(request.POST)
        if ChatsCreator.check_chat(request):
            chat = Chat()
            chat.title = request.POST.get('title')
            chat.save()
            chat.users.add(Authorization.get_user(request))
            users_id = request.POST.getlist('users')
            print(users_id)
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
            user = Authorization.get_user(request)
        except ObjectDoesNotExist:
            return redirect(reverse_lazy('main'))

        return render(request, 'main/user_settings.html', {'user': user})
