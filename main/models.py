from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class Message(models.Model):
    author = models.ForeignKey(User, null=False, default=None, on_delete=models.PROTECT)
    chat = models.ForeignKey('Chat', null=False, default=None, on_delete=models.CASCADE)
    message = models.TextField(null=False, blank=False, verbose_name='Message')
    date = models.DateField(auto_now=True, verbose_name='Published date')

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ['-date']

    def __str__(self):
        s = str(self.author) + '\n'
        s += str(self.message) + '\n'
        s += str(self.date)
        return s


class Chat(models.Model):
    title = models.CharField(max_length=30, verbose_name='Chat name')
    users = models.ManyToManyField(User, verbose_name='Chat members')

    def __str__(self):
        s = ''
        s += str(self.title)+'\nUsers:'
        for user in range(len(self.users.all())):
            s += self.users.all()[user].username + ' '
        return s


