from django.db import models
from django.contrib.auth.models import User

from django.core.validators import ValidationError


# Create your models here.


class Message(models.Model):
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    chat = models.ForeignKey('Chat', on_delete=models.CASCADE)
    data = models.ForeignKey('MessageData', on_delete=models.CASCADE)
    type = models.CharField(choices=(('text', 'text'), ('image', 'image'),
                                     ('video', 'video'), ('file', 'file')), max_length=10)
    date = models.DateTimeField(auto_now=True, verbose_name='Published date')
    id = models.AutoField(primary_key=True, verbose_name='Id')

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ['-date']

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

    def __str__(self):
        s = str(self.author) + '\n'
        if str(self.type) == 'text':
            s += str(self.data.text) + '\n'
        s += str(self.date)
        return s


class MessageData(models.Model):
    text = models.TextField(null=True, verbose_name='Text')
    file = models.FileField(null=True, verbose_name='File')
    id = models.AutoField(primary_key=True, verbose_name='Id')

    def delete(self, *args, **kwargs):
        self.file.delete()
        return super().delete(*args, **kwargs)


class Chat(models.Model):
    title = models.CharField(max_length=30, verbose_name='Chat name')
    users = models.ManyToManyField(User, verbose_name='Chat members')
    admin = models.ForeignKey(User, null=True, related_name='admin', on_delete=models.PROTECT)
    id = models.AutoField(primary_key=True, verbose_name='Id')

    def __str__(self):
        return str(self.title)

    def delete(self, using=None, keep_parents=False):
        messages = Message.objects.filter(chat=self)
        for message in messages:
            message.delete()

        return super().delete(using, keep_parents)


def validate_user_empty(user: User):
    if not user.username or not user.password or not user.email:
        raise ValidationError('Error during authorization data validation', params={'user': user})


def validate_user_username(user: User):
    if (user.username == '') or (user.username[0].isdigit()) or (len(user.username) < 2):
        raise ValidationError('Your name is too short or starts with a digit', params={'user': user})


def validate_user_password(user: User):
    if len(user.password) < 6 or user.password.lower().find(user.username.lower()) != -1:
        raise ValidationError('Your password is too short or contains your username')


def validate_user_username_is_unique(user: User):
    if User.objects.filter(username=user.username).count() > 0:
        raise ValidationError('This username is already used')


def validate_user_email_unique(user: User):
    if User.objects.filter(email=user.email).count() > 0:
        raise ValidationError('This mail is already used')


def validate_chat_title(chat: Chat):
    if len(chat.title) < 2:
        raise ValidationError('Chat title must be longer than 2')


class UserValidator:
    validators = [
        validate_user_empty,
        validate_user_username,
        validate_user_username_is_unique,
        validate_user_password,
        validate_user_email_unique,
    ]

    @staticmethod
    def validate_user(user: User):
        for validator in UserValidator.validators:
            validator(user)


class ChatValidator:
    validators = [
        validate_chat_title
    ]

    @staticmethod
    def validate_chat(chat: Chat):
        for validator in ChatValidator.validators:
            validator(chat)
