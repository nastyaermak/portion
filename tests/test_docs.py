"""Документація API доступна і описує ресурс «Рецепти»."""

import pytest


@pytest.mark.django_db
def test_schema_describes_recipes(api_client):
    response = api_client.get("/api/schema", {"format": "json"})

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths["/api/recipes"]) >= {"get", "post"}
    assert set(paths["/api/recipes/{id}"]) >= {"get", "patch", "delete"}


@pytest.mark.django_db
def test_swagger_page_opens(api_client):
    response = api_client.get("/api/docs")

    assert response.status_code == 200


@pytest.mark.django_db
def test_redoc_page_opens(api_client):
    response = api_client.get("/api/redoc")

    assert response.status_code == 200
