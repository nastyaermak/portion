from django.contrib import admin

from .models import (
    Category,
    Cuisine,
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeStep,
)


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0


class RecipeStepInline(admin.TabularInline):
    model = RecipeStep
    extra = 0


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "category", "cuisine", "servings"]
    inlines = [RecipeIngredientInline, RecipeStepInline]


admin.site.register([Category, Cuisine, Ingredient])
