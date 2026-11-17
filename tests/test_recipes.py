"""Тести ресурсу «Рецепти»: /api/recipes і /api/recipes/{id}.

Ресурс підтримує GET, POST, PATCH, DELETE; читати може кожен, створювати —
тільки залогінені, а змінювати й видаляти — автор рецепта або адміністратор.
"""

import pytest

from recipes.models import Recipe

LIST_URL = "/api/recipes"


def detail_url(pk):
    return f"/api/recipes/{pk}"


# ---------- GET: каталог ----------


@pytest.mark.django_db
def test_list_is_public(api_client, recipe):
    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.data["count"] == 1
    item = response.data["results"][0]
    assert item["title"] == "Омлет зі шпинатом"
    assert item["author"]["display_name"] == "Oleh"


@pytest.mark.django_db
def test_list_counts_nutrition_per_serving(api_client, recipe):
    """(200 г яєць + 150 г шпинату) / 2 порції."""
    item = api_client.get(LIST_URL).data["results"][0]

    assert item["nutrition_per_serving"] == {
        "kcal": 172,
        "protein": 15.2,
        "fat": 11.3,
        "carbs": 3.8,
    }


@pytest.mark.django_db
def test_list_search_and_filters(api_client, recipe):
    assert api_client.get(LIST_URL, {"search": "ОМЛЕТ"}).data["count"] == 1
    assert api_client.get(LIST_URL, {"search": "борщ"}).data["count"] == 0
    assert api_client.get(LIST_URL, {"max_kcal": 100}).data["count"] == 0
    assert api_client.get(LIST_URL, {"max_kcal": 200}).data["count"] == 1


@pytest.mark.django_db
def test_list_unknown_sort_is_400(api_client, recipe):
    response = api_client.get(LIST_URL, {"sort": "price"})

    assert response.status_code == 400
    assert response.data["error"] == "validation_error"
    assert "sort" in response.data["fields"]


@pytest.mark.django_db
def test_list_non_numeric_filter_is_400(api_client):
    response = api_client.get(LIST_URL, {"max_kcal": "багато"})

    assert response.status_code == 400
    assert response.data["fields"]["max_kcal"] == "Має бути числом"


# ---------- GET: один рецепт ----------


@pytest.mark.django_db
def test_detail_is_public(api_client, recipe):
    response = api_client.get(detail_url(recipe.id))

    assert response.status_code == 200
    assert response.data["steps"] == ["Збити яйця", "Посмажити"]
    assert len(response.data["ingredients"]) == 2


@pytest.mark.django_db
def test_detail_not_found(api_client):
    response = api_client.get(detail_url(999))

    assert response.status_code == 404
    assert response.data["message"] == "Рецепта з id 999 немає"


# ---------- POST: створення ----------


@pytest.mark.django_db
def test_create_recipe(author_client, author, recipe_payload):
    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 201
    assert response.data["title"] == "Яєчня"
    # Автор — той, хто залогінений, а не той, кого передали в тілі
    assert response.data["author"]["id"] == author.id
    assert response.data["steps"] == recipe_payload["steps"]
    assert Recipe.objects.filter(title="Яєчня").exists()


@pytest.mark.django_db
def test_create_without_login_is_401(api_client, recipe_payload):
    response = api_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 401
    assert response.data["error"] == "not_authenticated"
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_create_with_invalid_token_is_401(api_client, recipe_payload):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

    response = api_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 401
    assert response.data["error"] == "token_not_valid"


@pytest.mark.django_db
def test_create_with_empty_title_is_400(author_client, recipe_payload):
    recipe_payload["title"] = "   "

    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 400
    assert "title" in response.data["fields"]
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_create_with_zero_servings_is_400(author_client, recipe_payload):
    recipe_payload["servings"] = 0

    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 400
    assert "servings" in response.data["fields"]


@pytest.mark.django_db
def test_create_with_unknown_category_is_400(author_client, recipe_payload):
    recipe_payload["category_id"] = 999

    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 400
    assert response.data["fields"]["category_id"] == "Категорії з id 999 немає"


@pytest.mark.django_db
def test_create_with_unknown_ingredient_is_400(author_client, recipe_payload):
    recipe_payload["ingredients"] = [{"ingredient_id": 999, "amount_g": 10}]

    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 400
    assert "ingredients[0].ingredient_id" in response.data["fields"]


@pytest.mark.django_db
def test_create_without_steps_is_400(author_client, recipe_payload):
    recipe_payload["steps"] = []

    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 400
    assert "steps" in response.data["fields"]


@pytest.mark.django_db
def test_create_without_ingredients_is_400(author_client, recipe_payload):
    recipe_payload["ingredients"] = []

    response = author_client.post(LIST_URL, recipe_payload, format="json")

    assert response.status_code == 400
    assert "ingredients" in response.data["fields"]


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_author_can_update_own_recipe(author_client, recipe):
    response = author_client.patch(
        detail_url(recipe.id), {"servings": 4}, format="json"
    )

    assert response.status_code == 200
    assert response.data["servings"] == 4
    # Порцій стало вдвічі більше — калорій на порцію вдвічі менше
    assert response.data["nutrition_per_serving"]["kcal"] == 86


@pytest.mark.django_db
def test_update_replaces_steps(author_client, recipe):
    response = author_client.patch(
        detail_url(recipe.id), {"steps": ["Один крок"]}, format="json"
    )

    assert response.status_code == 200
    assert response.data["steps"] == ["Один крок"]


@pytest.mark.django_db
def test_other_user_cannot_update_recipe(other_client, recipe):
    response = other_client.patch(
        detail_url(recipe.id), {"title": "Чужий омлет"}, format="json"
    )

    assert response.status_code == 403
    assert response.data["error"] == "permission_denied"
    recipe.refresh_from_db()
    assert recipe.title == "Омлет зі шпинатом"


@pytest.mark.django_db
def test_admin_can_update_any_recipe(admin_client, recipe):
    response = admin_client.patch(
        detail_url(recipe.id), {"title": "Омлет від адміна"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["title"] == "Омлет від адміна"


@pytest.mark.django_db
def test_update_without_login_is_401(api_client, recipe):
    response = api_client.patch(
        detail_url(recipe.id), {"title": "x"}, format="json"
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_update_with_invalid_data_is_400(author_client, recipe):
    response = author_client.patch(
        detail_url(recipe.id), {"servings": 0}, format="json"
    )

    assert response.status_code == 400
    assert "servings" in response.data["fields"]


@pytest.mark.django_db
def test_update_missing_recipe_is_404(author_client):
    response = author_client.patch(
        detail_url(999), {"title": "x"}, format="json"
    )

    assert response.status_code == 404


# ---------- DELETE ----------


@pytest.mark.django_db
def test_author_can_delete_own_recipe(author_client, recipe):
    response = author_client.delete(detail_url(recipe.id))

    assert response.status_code == 204
    assert not Recipe.objects.filter(pk=recipe.id).exists()


@pytest.mark.django_db
def test_other_user_cannot_delete_recipe(other_client, recipe):
    response = other_client.delete(detail_url(recipe.id))

    assert response.status_code == 403
    assert Recipe.objects.filter(pk=recipe.id).exists()


@pytest.mark.django_db
def test_admin_can_delete_any_recipe(admin_client, recipe):
    response = admin_client.delete(detail_url(recipe.id))

    assert response.status_code == 204


@pytest.mark.django_db
def test_delete_without_login_is_401(api_client, recipe):
    response = api_client.delete(detail_url(recipe.id))

    assert response.status_code == 401
    assert Recipe.objects.filter(pk=recipe.id).exists()


@pytest.mark.django_db
def test_delete_missing_recipe_is_404(author_client):
    response = author_client.delete(detail_url(999))

    assert response.status_code == 404


@pytest.mark.django_db
def test_unsupported_method_is_405(author_client, recipe):
    response = author_client.put(detail_url(recipe.id), {}, format="json")

    assert response.status_code == 405
    assert response.data["error"] == "method_not_allowed"


# ---------- Логи ----------


@pytest.mark.django_db
def test_create_and_delete_are_logged(author_client, recipe_payload, caplog):
    caplog.set_level("INFO", logger="portion")

    created = author_client.post(LIST_URL, recipe_payload, format="json")
    author_client.delete(detail_url(created.data["id"]))

    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("Recipe created") for m in messages)
    assert any(m.startswith("Recipe deleted") for m in messages)


@pytest.mark.django_db
def test_forbidden_action_is_logged_as_warning(other_client, recipe, caplog):
    caplog.set_level("INFO", logger="portion")

    other_client.delete(detail_url(recipe.id))

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings
    assert "403" in warnings[0].getMessage()
