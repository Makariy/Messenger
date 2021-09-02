from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy


class StringHasher:
    @staticmethod
    def get_hash(s):
        number = 0
        for letter in s:
            number += ((ord(letter)**2) << 2 >> 1)

        result = str(number)
        ret = ''
        for i in range(0, len(result), 2):
            ret += chr(int(result[i] + result[i+1]))

        return ret


class PageBase:
    def __init__(self):
        pass

    def handle(self, request: HttpRequest, *params, **args):
        if request.method == 'POST':
            ret = self.post(request, *params, **args)
            if not ret:
                return HttpResponse('')
            return ret
        else:
            ret = self.get(request, *params, **args)
            if not ret:
                return HttpResponse('')
            return ret

    def post(self, request: HttpRequest, *params, **args) -> HttpResponse:
        return HttpResponse()

    def get(self, request: HttpRequest, *params, **args) -> HttpResponse:
        return HttpResponse()

    def set_cookies(self, response, cookies={}, **kwargs):
        if not cookies == {}:
            if not isinstance(cookies, type({})):
                raise TypeError('Parameter cookies was not the correct type: type(cookies) = ' + str(type(cookies)))
            else:
                for key in cookies:
                    response.set_cookie(key, cookies[key])
        else:
            for key in kwargs:
                response.set_cookie(key, cookies[key])

    def redirect(self, page, cookies={}, **kwargs):
        ret = redirect(reverse_lazy(page))
        if not cookies == {}:
            self.set_cookies(ret, cookies)
        else:
            self.set_cookies(ret, **kwargs)
        return ret




