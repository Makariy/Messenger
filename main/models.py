from django.db import models


# Create your models here.


class Message(models.Model):
    author = models.ForeignKey('User', null=False, default=None, on_delete=models.PROTECT)
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
    users = models.ManyToManyField('User', verbose_name='Chat members')

    def __str__(self):
        s = ''
        s += str(self.title)+'\nUsers:'
        for user in range(len(self.users.all())):
            s += self.users.all()[user].name + ' '
        return s


class User(models.Model):
    name = models.CharField(max_length=40, null=False, db_index=True, verbose_name='Name')
    password = models.CharField(max_length=40, null=False, db_index=False, verbose_name='Password')
    mail = models.EmailField(null=True, verbose_name='E-Mail')
    registered_date = models.DateField(auto_now=True, verbose_name='Registered date')

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-name']

    def __str__(self):
        return str(self.name)

