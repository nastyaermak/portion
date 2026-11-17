from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from config.errors import not_found_view

urlpatterns = [
    path("admin/", admin.site.urls),
    # Документація API: OpenAPI-схема, Swagger UI і ReDoc
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    path("api/", include("users.urls")),
    path("api/", include("recipes.urls")),
    # Невідомі адреси API теж відповідають JSON у загальному форматі помилки
    re_path(r"^api/", not_found_view),
]

handler404 = "config.errors.not_found_view"
handler500 = "config.errors.server_error_view"
