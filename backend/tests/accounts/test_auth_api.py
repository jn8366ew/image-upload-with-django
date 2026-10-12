import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

PASSWORD = "correct-horse-42"


@pytest.fixture
def api():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="alice", password=PASSWORD)


def csrf_post(api, path, data=None):
    api.get("/api/auth/csrf")
    token = api.cookies["csrftoken"].value
    return api.post(path, data, format="json", HTTP_X_CSRFTOKEN=token)


def test_auth_user_model_is_custom():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model()._meta.label == "accounts.User"


def test_csrf_endpoint_sets_cookie(api):
    response = api.get("/api/auth/csrf")

    assert response.status_code == 204
    assert response.cookies["csrftoken"].value


@pytest.mark.django_db
def test_login_creates_session(api, user):
    response = csrf_post(api, "/api/auth/login", {"username": "alice", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json() == {"username": "alice"}
    assert api.session["_auth_user_id"] == str(user.pk)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("username", "password", "active"),
    [
        ("nobody", PASSWORD, True),
        ("alice", "wrong-password", True),
        ("alice", PASSWORD, False),
    ],
    ids=["unknown_user", "wrong_password", "inactive_user"],
)
def test_inactive_user_gets_same_invalid_credentials_response(
    api, user, username, password, active
):
    user.is_active = active
    user.save()

    response = csrf_post(api, "/api/auth/login", {"username": username, "password": password})

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid credentials"}
    assert "_auth_user_id" not in api.session


@pytest.mark.django_db
def test_login_rotates_csrf_token(api, user):
    api.get("/api/auth/csrf")
    before = api.cookies["csrftoken"].value

    api.post(
        "/api/auth/login",
        {"username": "alice", "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=before,
    )

    assert api.cookies["csrftoken"].value != before


@pytest.mark.django_db
def test_logout_clears_session(api, user):
    api.force_login(user)

    response = csrf_post(api, "/api/auth/logout")

    assert response.status_code == 204
    assert "_auth_user_id" not in api.session


@pytest.mark.django_db
def test_logout_rejects_get(api, user):
    api.force_login(user)

    response = api.get("/api/auth/logout")

    assert response.status_code == 405
    assert "_auth_user_id" in api.session


@pytest.mark.django_db
def test_me_requires_authentication(api, user):
    assert api.get("/api/auth/me").status_code == 403

    api.force_login(user)
    response = api.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"username": "alice"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "logged_in"),
    [("/api/auth/login", False), ("/api/auth/logout", True)],
    ids=["login", "logout"],
)
def test_post_without_csrf_is_rejected(api, user, path, logged_in):
    if logged_in:
        api.force_login(user)
    api.get("/api/auth/csrf")

    response = api.post(path, {"username": "alice", "password": PASSWORD}, format="json")

    assert response.status_code == 403
    assert response["Content-Type"] == "application/json"
    assert response.json()["detail"].startswith("CSRF Failed")
    assert ("_auth_user_id" in api.session) is logged_in
