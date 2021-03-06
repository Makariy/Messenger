# Generated by Django 3.2.5 on 2021-08-09 11:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Chat',
            fields=[
                ('title', models.CharField(max_length=30, verbose_name='Chat name')),
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='Id')),
                ('users', models.ManyToManyField(to=settings.AUTH_USER_MODEL, verbose_name='Chat members')),
            ],
        ),
        migrations.CreateModel(
            name='MessageData',
            fields=[
                ('text', models.TextField(null=True, verbose_name='Text')),
                ('image', models.ImageField(null=True, upload_to='', verbose_name='Image')),
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='Id')),
            ],
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('type', models.CharField(choices=[('text', 'text'), ('image', 'image')], max_length=10)),
                ('date', models.DateTimeField(auto_now=True, verbose_name='Published date')),
                ('id', models.AutoField(primary_key=True, serialize=False, verbose_name='Id')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('chat', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.chat')),
                ('data', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.messagedata')),
            ],
            options={
                'verbose_name': 'Message',
                'verbose_name_plural': 'Messages',
                'ordering': ['-date'],
            },
        ),
    ]
