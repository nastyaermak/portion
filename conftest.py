"""Спільні фікстури для тестів.

Кожен тест отримує чисту тестову базу (pytest-django), тому дані
створюються фікстурами тут, а не беруться з demo.json.
"""

import pytest
from rest_framework.test import APIClient

from recipes.models import (
    Category,
    Cuisine,
    Ingredient,
    Recipe,
    RecipeIngredient,
    RecipeStep,
)
from users.models import User

PASSWORD = "Sup3r-secret-pass"


def make_user(username, **extra):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=PASSWORD,
        display_name=username.capitalize(),
        **extra,
    )


def client_for(user):
    """Входить через /api/auth/login і повертає клієнт з access-токеном."""
    client = APIClient()
    tokens = client.post(
        "/api/auth/login",
        {"username": user.username, "password": PASSWORD},
        format="json",
    ).data
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
    return client


@pytest.fixture
def api_client():
    """Клієнт без входу (анонімний відвідувач)."""
    return APIClient()


@pytest.fixture
def author(db):
    return make_user("oleh")


@pytest.fixture
def other_user(db):
    return make_user("maria")


@pytest.fixture
def admin_user(db):
    return make_user("nastya", is_staff=True)


@pytest.fixture
def author_client(author):
    return client_for(author)


@pytest.fixture
def other_client(other_user):
    return client_for(other_user)


@pytest.fixture
def admin_client(admin_user):
    return client_for(admin_user)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Сніданки")


@pytest.fixture
def cuisine(db):
    return Cuisine.objects.create(name="Українська")


@pytest.fixture
def egg(db):
    return Ingredient.objects.create(
        name="Яйце",
        kcal_100g=155,
        protein_100g=13,
        fat_100g=11,
        carbs_100g=1.1,
    )


@pytest.fixture
def spinach(db):
    return Ingredient.objects.create(
        name="Шпинат",
        kcal_100g=23,
        protein_100g=2.9,
        fat_100g=0.4,
        carbs_100g=3.6,
    )


@pytest.fixture
def recipe(author, category, cuisine, egg, spinach):
    """Рецепт автора oleh: 200 г яєць + 150 г шпинату на 2 порції."""
    recipe = Recipe.objects.create(
        author=author,
        category=category,
        cuisine=cuisine,
        title="Омлет зі шпинатом",
        servings=2,
        cook_time_min=10,
    )
    RecipeIngredient.objects.create(recipe=recipe, ingredient=egg, amount_g=200)
    RecipeIngredient.objects.create(
        recipe=recipe, ingredient=spinach, amount_g=150
    )
    RecipeStep.objects.create(recipe=recipe, position=1, text="Збити яйця")
    RecipeStep.objects.create(recipe=recipe, position=2, text="Посмажити")
    return recipe


@pytest.fixture
def recipe_payload(category, cuisine, egg, spinach):
    """Коректні дані для створення рецепта."""
    return {
        "title": "Яєчня",
        "description": "Найпростіший сніданок",
        "cook_time_min": 5,
        "servings": 1,
        "category_id": category.id,
        "cuisine_id": cuisine.id,
        "ingredients": [
            {"ingredient_id": egg.id, "amount_g": 100, "note": "2 шт."},
            {"ingredient_id": spinach.id, "amount_g": 50},
        ],
        "steps": ["Розбити яйця на сковорідку", "Смажити 3 хвилини"],
    }
