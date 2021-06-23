from django import forms
from django.db import models

from .models import User
from .models import Chat

class UserForm(forms.ModelForm):
    password = forms.CharField(max_length=30, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('name', 'password', 'mail')

