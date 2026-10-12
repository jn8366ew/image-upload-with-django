import uuid

import boto3
import pytest
from botocore.config import Config
from django.conf import settings

PREFIX = "attachments/contract-test/"


@pytest.fixture
def bucket() -> str:
    if not settings.S3_BUCKET:
        pytest.fail("S3_BUCKET이 비어 있습니다. .env에 dev 버킷 이름을 넣으세요.")
    return settings.S3_BUCKET


@pytest.fixture
def s3():
    # 셋 중 하나라도 빠지면 presign URL이 전역 엔드포인트로 나와 307이 납니다.
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


@pytest.fixture
def new_key(s3, bucket):
    keys: list[str] = []

    def make() -> str:
        key = f"{PREFIX}{uuid.uuid4()}.png"
        keys.append(key)
        return key

    yield make
    for key in keys:
        s3.delete_object(Bucket=bucket, Key=key)
