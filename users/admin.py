from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PortionUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'display_name', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        ('Профіль', {'fields': ['display_name', 'bio', 'avatar_url']}),
        ('Денна ціль', {'fields': ['kcal_goal', 'protein_goal', 'fat_goal', 'carbs_goal']}),
    )
