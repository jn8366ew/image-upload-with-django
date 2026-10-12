from collections.abc import Callable
from dataclasses import dataclass

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from attachments.storage.fake import InMemoryStorageGateway
from attachments.storage.s3 import build_s3_gateway

BUCKET = "test-bucket"
REGION = "ap-northeast-2"


@pytest.fixture
def aws(monkeypatch, settings):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    settings.AWS_REGION = REGION
    settings.S3_BUCKET = BUCKET
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
        )
        yield client


@dataclass
class Store:
    gateway: object
    put: Callable[[str, bytes, str], None]
    bucket: str
    fail_delete: Callable[[str], None]
    sent_ranges: list[str] | None = None


@pytest.fixture(params=["fake", "s3"])
def store(request):
    if request.param == "fake":
        fake = InMemoryStorageGateway()
        return Store(fake, fake.put, fake.bucket, fake.fail_delete_for.add)

    client = request.getfixturevalue("aws")

    def put(key: str, body: bytes, content_type: str) -> None:
        client.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType=content_type)

    gateway = build_s3_gateway()
    sent_ranges: list[str] = []
    gateway._client.meta.events.register(
        "before-send.s3.GetObject",
        lambda request, **_: sent_ranges.append(request.headers.get("Range", b"").decode()),
    )

    def fail_delete(key: str) -> None:
        error = {"Error": {"Code": "AccessDenied", "Message": "denied"}}

        def denied(**_):
            raise ClientError(error, "DeleteObject")

        gateway._client.delete_object = denied

    return Store(gateway, put, BUCKET, fail_delete, sent_ranges)
