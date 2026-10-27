from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    """Категорія страви: суп, салат, сніданок, десерт…"""

    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Cuisine(models.Model):
    """Кухня: українська, італійська, азійська…"""

    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'cuisines'
        ordering = ['name']

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    """Інгредієнт з КБЖВ на 100 г."""

    name = models.CharField(max_length=100, unique=True)
    kcal_100g = models.DecimalField(max_digits=6, decimal_places=1, validators=[MinValueValidator(0)])
    protein_100g = models.DecimalField(max_digits=5, decimal_places=1, validators=[MinValueValidator(0)])
    fat_100g = models.DecimalField(max_digits=5, decimal_places=1, validators=[MinValueValidator(0)])
    carbs_100g = models.DecimalField(max_digits=5, decimal_places=1, validators=[MinValueValidator(0)])

    class Meta:
        db_table = 'ingredients'
        ordering = ['name']

    def __str__(self):
        return self.name


class Recipe(models.Model):
    """Рецепт; КБЖВ не зберігається, а рахується з інгредієнтів."""

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recipes')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='recipes')
    cuisine = models.ForeignKey(Cuisine, on_delete=models.PROTECT, related_name='recipes')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    servings = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    cook_time_min = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'recipes'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class RecipeStep(models.Model):
    """Крок приготування; position — порядковий номер кроку."""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='steps')
    position = models.PositiveIntegerField()
    text = models.TextField()

    class Meta:
        db_table = 'recipe_steps'
        ordering = ['position']
        unique_together = [('recipe', 'position')]


class RecipeIngredient(models.Model):
    """Скільки грамів інгредієнта в рецепті; note — як показати людині («2 шт.»)."""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='recipe_ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='recipe_ingredients')
    amount_g = models.DecimalField(max_digits=7, decimal_places=1, validators=[MinValueValidator(Decimal('0.1'))])
    note = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'recipe_ingredients'
        ordering = ['id']
        unique_together = [('recipe', 'ingredient')]
