"""Сторінки списків у форматі з README: {"count", "page", "page_size", "results"}."""

from rest_framework.exceptions import ValidationError

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def positive_int(request, name, default=None, maximum=None):
    """Читає з query-параметрів додатне ціле число; інакше 400."""
    raw = request.query_params.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError({name: 'Має бути цілим числом'})
    if value < 1:
        raise ValidationError({name: 'Має бути більше 0'})
    if maximum is not None and value > maximum:
        raise ValidationError({name: f'Не більше {maximum}'})
    return value


def paginate(request, queryset, serializer_class):
    """Повертає одну сторінку списку; сторінка за межами списку — порожній results."""
    page = positive_int(request, 'page', default=1)
    page_size = positive_int(request, 'page_size', default=DEFAULT_PAGE_SIZE, maximum=MAX_PAGE_SIZE)
    start = (page - 1) * page_size
    return {
        'count': queryset.count(),
        'page': page,
        'page_size': page_size,
        'results': serializer_class(queryset[start:start + page_size], many=True).data,
    }
