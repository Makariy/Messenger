from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class Message(models.Model):
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    chat = models.ForeignKey('Chat', on_delete=models.CASCADE)
    data = models.ForeignKey('MessageData', on_delete=models.CASCADE)
    type = models.CharField(choices=(('text', 'text'), ('image', 'image')), max_length=10)
    date = models.DateTimeField(auto_now=True, verbose_name='Published date')
    id = models.AutoField(primary_key=True, verbose_name='Id')

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ['-date']

    def delete(self, *args, **kwargs):
        self.data.delete()
        super().delete(*args, **kwargs)

    def __str__(self):
        s = str(self.author) + '\n'
        if str(self.type) == 'text':
            s += str(self.data.text) + '\n'
        s += str(self.date)
        return s


class MessageData(models.Model):
    text = models.TextField(null=True, verbose_name='Text')
    image = models.ImageField(null=True, verbose_name='Image')
    id = models.AutoField(primary_key=True, verbose_name='Id')

    def delete(self, *args, **kwargs):
        self.image.delete()
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


