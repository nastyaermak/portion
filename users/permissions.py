"""Права доступу до ендпоінтів.

Неавторизований запит на зміну даних отримує 401, авторизований без
потрібних прав — 403 (це розрізняє сам DRF: якщо токена немає або він
невалідний, відповідь буде 401).
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_staff)


class IsAuthenticatedOrReadOnly(BasePermission):
    """Читати можуть усі, змінювати — тільки залогінені."""

    message = "Увійдіть в акаунт, щоб виконати цю дію"

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)


class IsAdminOrReadOnly(BasePermission):
    """Читати можуть усі, змінювати — тільки адміністратор."""

    message = "Змінювати ці дані може тільки адміністратор"

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return is_admin(request.user)


class IsAuthorOrAdminOrReadOnly(BasePermission):
    """Редагувати й видаляти рецепт може його автор або адміністратор."""

    message = "Редагувати й видаляти можна тільки власні рецепти"

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.author_id == request.user.id or is_admin(request.user)
