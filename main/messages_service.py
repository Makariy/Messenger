from django.contrib.auth.models import User

from .models import Message, MessageData, Chat


def get_last_messages(chat=None, chat_title=None, count=10, last_id=-1):
    """Returns last <count> starting from <last_id> (if specified) messages <main.models.Message>
     from <chat> or chat with title <chat_title>, if <chat> or <chat_title> is not specified, raises ValueError"""
    if not chat_title and not chat:
        raise ValueError

    if chat:
        messages = Message.objects.filter(chat=chat).order_by('-id')
    if chat_title:
        messages = Message.objects.filter(chat__title=chat_title).order_by('-id')

    start_index = 0
    if last_id is not -1:
        for i in range(len(messages)):
            if messages[i].id == int(last_id):
                start_index = i + 1
                break

    messages = messages[start_index:start_index+count]
    return messages[::-1]


def get_last_chats_messages(chats):
    """Returns the last messages <main.models.Message> from chats <chats>"""
    return [Message.objects.filter(chat=chat).order_by('pk').last() for chat in chats]


