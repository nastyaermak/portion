"""Єдиний формат помилок для всього API: {"error": ..., "message": ..., "fields": {...}}."""

from django.http import Http404, JsonResponse
from rest_framework import exceptions, status
from rest_framework.views import exception_handler as drf_exception_handler

CODES = {
    400: ('validation_error', 'Перевірте введені дані'),
    404: ('not_found', 'Такого об\'єкта немає'),
    405: ('method_not_allowed', 'Цей метод не підтримується для цієї адреси'),
    409: ('conflict', 'Дію не можна виконати'),
    415: ('unsupported_media_type', 'Дані мають бути у форматі JSON'),
}


class Conflict(exceptions.APIException):
    """409: дію не можна виконати через інші дані (наприклад, у категорії є рецепти)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = CODES[409][1]
    default_code = 'conflict'


def error_body(status_code, message=None, fields=None, code=None):
    """Тіло відповіді з помилкою."""
    default_code, default_message = CODES.get(status_code, ('error', 'Сталася помилка'))
    return {
        'error': code or default_code,
        'message': message or default_message,
        'fields': fields or {},
    }


def flatten(detail, prefix=''):
    """Перетворює вкладені помилки серіалізатора на {"поле": "повідомлення"}.

    Помилки елементів списку отримують назву на кшталт "ingredients[1].amount_g".
    """
    result = {}
    if isinstance(detail, dict):
        for key, value in detail.items():
            name = key if key != 'non_field_errors' else ''
            result.update(flatten(value, f'{prefix}.{name}' if prefix and name else prefix or name))
    elif isinstance(detail, list):
        if all(not isinstance(item, (dict, list)) for item in detail):
            if detail:
                result[prefix or 'non_field_errors'] = str(detail[0])
        else:
            for index, item in enumerate(detail):
                result.update(flatten(item, f'{prefix}[{index}]'))
    else:
        result[prefix or 'non_field_errors'] = str(detail)
    return result


def exception_handler(exc, context):
    """Обробник помилок DRF, який приводить усі відповіді до одного формату."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound(str(exc) if str(exc) else None)
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        fields = flatten(exc.detail)
        message = fields.pop('non_field_errors', None)
        response.data = error_body(400, message=message, fields=fields)
    elif isinstance(exc, exceptions.ParseError):
        response.data = error_body(400, message='Тіло запиту — некоректний JSON', code='parse_error')
    elif isinstance(exc, exceptions.NotFound):
        message = exc.detail if exc.detail != exceptions.NotFound.default_detail else None
        response.data = error_body(404, message=message)
    elif isinstance(exc, exceptions.MethodNotAllowed):
        response.data = error_body(405, message=f'Метод {context["request"].method} не підтримується для цієї адреси')
    else:
        response.data = error_body(response.status_code, message=str(exc.detail))
    return response


def not_found_view(request, exception=None):
    """404 для адрес, яких немає в API (не DRF-в'юхи)."""
    return JsonResponse(error_body(404, message='Такої адреси в API немає'), status=404,
                        json_dumps_params={'ensure_ascii': False})


def server_error_view(request):
    """500 у тому ж форматі."""
    return JsonResponse(error_body(500, message='Помилка на сервері, спробуйте пізніше', code='server_error'),
                        status=500, json_dumps_params={'ensure_ascii': False})
