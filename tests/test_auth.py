"""Тести реєстрації, входу й профілю (/api/auth/*, /api/me)."""

import pytest

from conftest import PASSWORD


@pytest.mark.django_db
def test_register(api_client):
    response = api_client.post(
        "/api/auth/register",
        {
            "username": "ivan",
            "email": "ivan@example.com",
            "first_name": "Іван",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 201
    assert "password" not in response.data


@pytest.mark.django_db
def test_register_duplicate_username_is_rejected(api_client, author):
    response = api_client.post(
        "/api/auth/register",
        {
            "username": author.username,
            "email": "new@example.com",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["fields"]["username"] == "Такий username уже зайнятий"


@pytest.mark.django_db
def test_login_returns_tokens(api_client, author):
    response = api_client.post(
        "/api/auth/login",
        {"username": author.username, "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 200
    assert {"access", "refresh"} <= set(response.data)


@pytest.mark.django_db
def test_login_wrong_password_is_401_and_password_not_logged(
    api_client, author, caplog
):
    caplog.set_level("INFO", logger="portion")

    response = api_client.post(
        "/api/auth/login",
        {"username": author.username, "password": "wrong-pass-123"},
        format="json",
    )

    assert response.status_code == 401
    assert response.data["error"] == "invalid_credentials"
    assert "wrong-pass-123" not in caplog.text
    assert "Failed login" in caplog.text


@pytest.mark.django_db
def test_me_requires_login(api_client):
    assert api_client.get("/api/me").status_code == 401


@pytest.mark.django_db
def test_me_returns_profile(author_client, author):
    response = author_client.get("/api/me")

    assert response.status_code == 200
    assert response.data["username"] == author.username
