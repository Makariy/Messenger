FROM python:3.7-buster

RUN pip install --upgrade pip 
RUN pip install Pillow
RUN pip install django==3.1.*
RUN pip install websockets
RUN pip install asyncio

EXPOSE 8000 8001 8002


ADD . ./app
WORKDIR ./app

CMD python manage.py runserver 0.0.0.0:8000

