from django.apps import AppConfig
from django.db.backends.signals import connection_created


def unicode_lower(connection, **kwargs):
    """Вбудований LOWER у SQLite змінює регістр лише латиниці; підміняємо його на Python-версію,
    щоб пошук і перевірка унікальних назв працювали з кирилицею («Сирники» = «сирники»)."""
    if connection.vendor == 'sqlite':
        connection.connection.create_function(
            'LOWER', 1, lambda value: value.lower() if isinstance(value, str) else value, deterministic=True)


class RecipesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'recipes'

    def ready(self):
        connection_created.connect(unicode_lower)
