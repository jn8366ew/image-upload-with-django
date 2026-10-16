import uuid

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from attachments.models import Attachment
from attachments.storage.fake import InMemoryStorageGateway


@pytest.fixture(autouse=True)
def _clear_cache(db):
    cache.clear()


@pytest.fixture
def gateway():
    return InMemoryStorageGateway()


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="uploader", password="pw")


@pytest.fixture
def api(user, gateway, monkeypatch):
    monkeypatch.setattr("attachments.views.build_s3_gateway", lambda: gateway)
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def make_attachment(user):
    def make(owner=None, status=Attachment.Status.PENDING, ext=".png", **fields):
        owner = owner or user
        public_id = uuid.uuid4()
        fields.setdefault("original_filename", f"photo{ext}")
        return Attachment.objects.create(
            public_id=public_id,
            created_by=owner,
            s3_key=f"attachments/{owner.pk}/{public_id}{ext}",
            status=status,
            **fields,
        )

    return make


@pytest.fixture
def mongo_db(monkeypatch):
    from attachments.events import mongo

    default = mongo.database()
    db = default.client[f"test_{default.name}"]
    assert db.name.startswith("test_")
    db.client.drop_database(db.name)
    monkeypatch.setattr(mongo, "database", lambda: db)
    return db
