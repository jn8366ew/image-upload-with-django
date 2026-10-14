from collections.abc import Iterator
from contextlib import contextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from django.conf import settings

from attachments.exceptions import ObjectNotFound, StorageAuthError, StorageError
from attachments.storage.gateway import PresignedPost, StoredObject

AUTH_ERROR_CODES = frozenset(
    {
        "AccessDenied",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "RequestTimeTooSkewed",
        "InvalidSecurity",
        "AccountProblem",
        "ExpiredToken",
        "InvalidToken",
        "TokenRefreshRequired",
        "NoSuchBucket",
    }
)


@contextmanager
def _mapped_errors(key: str) -> Iterator[None]:
    try:
        yield
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchKey"):
            raise ObjectNotFound(key) from e
        if code in AUTH_ERROR_CODES:
            raise StorageAuthError(key) from e
        raise StorageError(key) from e
    except (NoCredentialsError, PartialCredentialsError) as e:
        raise StorageAuthError(key) from e


class S3StorageGateway:
    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def presign_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost:
        form = self._client.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=expires_in,
        )
        return PresignedPost(url=form["url"], fields=form["fields"])

    def head(self, key: str) -> str:
        with _mapped_errors(key):
            obj = self._client.head_object(Bucket=self._bucket, Key=key)
        return obj["ContentType"]

    def read_prefix(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=key, Range="bytes=0-7")
        return obj["Body"].read()

    def open(self, key: str) -> StoredObject:
        with _mapped_errors(key):
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
        return StoredObject(stream=obj["Body"], content_type=obj["ContentType"])

    def delete(self, key: str) -> None:
        with _mapped_errors(key):
            self._client.delete_object(Bucket=self._bucket, Key=key)


def build_s3_gateway() -> S3StorageGateway:
    client = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )
    return S3StorageGateway(client, settings.S3_BUCKET)
