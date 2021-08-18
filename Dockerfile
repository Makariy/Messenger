FROM python:3-onbuild 

ADD . ./app 
WORKDIR ./app 

RUN pip install --upgrade pip 
RUN pip install django==3.1.*
RUN pip install websockets
RUN pip install asyncio
RUN pip install Image

EXPOSE 8000 8001 8002

CMD python manage.py runserver 0.0.0.0:8000

