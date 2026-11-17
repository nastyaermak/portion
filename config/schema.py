"""Спільні описи для OpenAPI-документації (drf-spectacular)."""

from drf_spectacular.utils import OpenApiExample, OpenApiResponse
from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    """Формат усіх помилок API (див. config/errors.py)."""

    error = serializers.CharField(help_text="Код помилки, напр. not_found")
    message = serializers.CharField(help_text="Пояснення для людини")
    fields = serializers.DictField(
        child=serializers.CharField(),
        help_text="Помилки окремих полів: {\"поле\": \"повідомлення\"}",
    )


def error(description, code, message, fields=None):
    """Відповідь-помилка з прикладом."""
    return OpenApiResponse(
        response=ErrorSerializer,
        description=description,
        examples=[
            OpenApiExample(
                code,
                value={
                    "error": code,
                    "message": message,
                    "fields": fields or {},
                },
                response_only=True,
            )
        ],
    )


ERROR_400 = error(
    "Некоректні дані",
    "validation_error",
    "Перевірте введені дані",
    {"servings": "Кількість порцій має бути більше 0"},
)
ERROR_401 = error(
    "Немає токена або токен недійсний",
    "not_authenticated",
    "Увійдіть в акаунт, щоб виконати цю дію",
)
ERROR_403 = error(
    "Недостатньо прав (чужий рецепт)",
    "permission_denied",
    "Редагувати й видаляти можна тільки власні рецепти",
)
ERROR_404 = error("Рецепта немає", "not_found", "Рецепта з id 999 немає")
