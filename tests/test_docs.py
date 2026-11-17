"""Документація API доступна і описує ресурс «Рецепти»."""

import pytest

pytestmark = pytest.mark.django_db


def test_schema_describes_recipes(api_client):
    response = api_client.get("/api/schema", {"format": "json"})

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths["/api/recipes"]) >= {"get", "post"}
    assert set(paths["/api/recipes/{id}"]) >= {"get", "patch", "delete"}


@pytest.mark.parametrize("url", ["/api/docs", "/api/redoc"])
def test_docs_pages_open(api_client, url):
    assert api_client.get(url).status_code == 200
