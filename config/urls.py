from django.contrib import admin
from django.urls import include, path, re_path

from config.errors import not_found_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("recipes.urls")),
    # Невідомі адреси API теж відповідають JSON у загальному форматі помилки
    re_path(r"^api/", not_found_view),
]

handler404 = "config.errors.not_found_view"
handler500 = "config.errors.server_error_view"
