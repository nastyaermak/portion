"""Тести ресурсу «Рецепти»: /api/recipes і /api/recipes/{id}.

Ресурс підтримує GET, POST, PATCH, DELETE; читати може кожен, створювати —
тільки залогінені, а змінювати й видаляти — автор рецепта або адміністратор.
"""

import pytest

from recipes.models import Recipe

pytestmark = pytest.mark.django_db

LIST_URL = "/api/recipes"


def detail_url(pk):
    return f"/api/recipes/{pk}"


# ---------- GET: каталог ----------


def test_list_is_public(api_client, recipe):
    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.data["count"] == 1
    item = response.data["results"][0]
    assert item["title"] == "Омлет зі шпинатом"
    assert item["author"]["display_name"] == "Oleh"


def test_list_counts_nutrition_per_serving(api_client, recipe):
    """(200 г яєць + 150 г шпинату) / 2 порції."""
    item = api_client.get(LIST_URL).data["results"][0]

    assert item["nutrition_per_serving"] == {
        "kcal": 172,
        "protein": 15.2,
        "fat": 11.3,
        "carbs": 3.8,
    }


def test_list_search_and_filters(api_client, recipe):
    assert api_client.get(LIST_URL, {"search": "ОМЛЕТ"}).data["count"] == 1
    assert api_client.get(LIST_URL, {"search": "борщ"}).data["count"] == 0
    assert api_client.get(LIST_URL, {"max_kcal": 100}).data["count"] == 0
    assert api_client.get(LIST_URL, {"max_kcal": 200}).data["count"] == 1


def test_list_unknown_sort_is_400(api_client, recipe):
    response = api_client.get(LIST_URL, {"sort": "price"})

    assert response.status_code == 400
    assert response.data["error"] == "validation_error"
    assert "sort" in response.data["fields"]


def test_list_non_numeric_filter_is_400(api_client):
    response = api_client.get(LIST_URL, {"max_kcal": "багато"})

    assert response.status_code == 400
    assert response.data["fields"]["max_kcal"] == "Має бути числом"


# ---------- GET: один рецепт ----------


def test_detail_is_public(api_client, recipe):
    response = api_client.get(detail_url(recipe.id))

    assert response.status_code == 200
    assert response.data["steps"] == ["Збити яйця", "Посмажити"]
    assert len(response.data["ingredients"]) == 2


def test_detail_not_found(api_client):
    response = api_client.get(detail_url(999))

    assert response.status_code == 404
    assert response.data["message"] == "Рецепта з id 999 немає"


# ---------- POST: створення ----------


def test_create_recipe(author_client, author, recipe_payload):
    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 201
    assert response.data["title"] == "Яєчня"
    # Автор — той, хто залогінений, а не той, кого передали в тілі
    assert response.data["author"]["id"] == author.id
    assert response.data["steps"] == recipe_payload["steps"]
    assert Recipe.objects.filter(title="Яєчня").exists()


def test_create_without_login_is_401(api_client, recipe_payload):
    response = api_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 401
    assert response.data["error"] == "not_authenticated"
    assert not Recipe.objects.exists()


def test_create_with_invalid_token_is_401(api_client, recipe_payload):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

    response = api_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 401
    assert response.data["error"] == "token_not_valid"


@pytest.mark.parametrize(
    "change, field",
    [
        ({"title": "   "}, "title"),
        ({"servings": 0}, "servings"),
        ({"cook_time_min": -5}, "cook_time_min"),
        ({"category_id": 999}, "category_id"),
        ({"steps": []}, "steps"),
        ({"ingredients": []}, "ingredients"),
        (
            {"ingredients": [{"ingredient_id": 999, "amount_g": 10}]},
            "ingredients[0].ingredient_id",
        ),
        (
            {"ingredients": [{"ingredient_id": 1, "amount_g": 0}]},
            "ingredients[0].amount_g",
        ),
    ],
)
def test_create_with_invalid_data_is_400(
    author_client, recipe_payload, change, field
):
    payload = {**recipe_payload, **change}
    if field == "ingredients[0].amount_g":
        payload["ingredients"][0]["ingredient_id"] = recipe_payload[
            "ingredients"
        ][0]["ingredient_id"]

    response = author_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.data["fields"]
    assert not Recipe.objects.exists()


def test_create_with_duplicate_ingredient_is_400(
    author_client, recipe_payload, egg
):
    recipe_payload["ingredients"] = [
        {"ingredient_id": egg.id, "amount_g": 50},
        {"ingredient_id": egg.id, "amount_g": 70},
    ]

    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 400
    assert "ingredients" in response.data["fields"]


# ---------- PATCH: редагування ----------


def test_author_can_update_own_recipe(author_client, recipe):
    response = author_client.patch(
        detail_url(recipe.id), {"servings": 4}, format="json"
    )

    assert response.status_code == 200
    assert response.data["servings"] == 4
    # Порцій стало вдвічі більше — калорій на порцію вдвічі менше
    assert response.data["nutrition_per_serving"]["kcal"] == 86


def test_update_replaces_steps(author_client, recipe):
    response = author_client.patch(
        detail_url(recipe.id), {"steps": ["Один крок"]}, format="json"
    )

    assert response.status_code == 200
    assert response.data["steps"] == ["Один крок"]


def test_other_user_cannot_update_recipe(other_client, recipe):
    response = other_client.patch(
        detail_url(recipe.id), {"title": "Чужий омлет"}, format="json"
    )

    assert response.status_code == 403
    assert response.data["error"] == "permission_denied"
    recipe.refresh_from_db()
    assert recipe.title == "Омлет зі шпинатом"


def test_admin_can_update_any_recipe(admin_client, recipe):
    response = admin_client.patch(
        detail_url(recipe.id), {"title": "Омлет від адміна"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["title"] == "Омлет від адміна"


def test_update_without_login_is_401(api_client, recipe):
    response = api_client.patch(
        detail_url(recipe.id), {"title": "x"}, format="json"
    )

    assert response.status_code == 401


def test_update_with_invalid_data_is_400(author_client, recipe):
    response = author_client.patch(
        detail_url(recipe.id), {"servings": 0}, format="json"
    )

    assert response.status_code == 400
    assert "servings" in response.data["fields"]


def test_update_missing_recipe_is_404(author_client):
    response = author_client.patch(
        detail_url(999), {"title": "x"}, format="json"
    )

    assert response.status_code == 404


# ---------- DELETE ----------


def test_author_can_delete_own_recipe(author_client, recipe):
    response = author_client.delete(detail_url(recipe.id))

    assert response.status_code == 204
    assert not Recipe.objects.filter(pk=recipe.id).exists()


def test_other_user_cannot_delete_recipe(other_client, recipe):
    response = other_client.delete(detail_url(recipe.id))

    assert response.status_code == 403
    assert Recipe.objects.filter(pk=recipe.id).exists()


def test_admin_can_delete_any_recipe(admin_client, recipe):
    response = admin_client.delete(detail_url(recipe.id))

    assert response.status_code == 204


def test_delete_without_login_is_401(api_client, recipe):
    response = api_client.delete(detail_url(recipe.id))

    assert response.status_code == 401
    assert Recipe.objects.filter(pk=recipe.id).exists()


def test_delete_missing_recipe_is_404(author_client):
    response = author_client.delete(detail_url(999))

    assert response.status_code == 404


def test_unsupported_method_is_405(author_client, recipe):
    response = author_client.put(detail_url(recipe.id), {}, format="json")

    assert response.status_code == 405
    assert response.data["error"] == "method_not_allowed"


# ---------- Логи ----------


def test_create_and_delete_are_logged(author_client, recipe_payload, caplog):
    caplog.set_level("INFO", logger="portion")

    created = author_client.post(LIST_URL, recipe_payload, format="json")
    author_client.delete(detail_url(created.data["id"]))

    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("Recipe created") for m in messages)
    assert any(m.startswith("Recipe deleted") for m in messages)


def test_forbidden_action_is_logged_as_warning(other_client, recipe, caplog):
    caplog.set_level("INFO", logger="portion")

    other_client.delete(detail_url(recipe.id))

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings
    assert "403" in warnings[0].getMessage()
