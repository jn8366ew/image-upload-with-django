import time

import pytest
import urllib3
from botocore.exceptions import ClientError
from django.conf import settings

pytestmark = pytest.mark.s3

MAX_BYTES = 2_621_440
FRONTEND_ORIGIN = "http://localhost:5173"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

http = urllib3.PoolManager()


def png_bytes(size: int) -> bytes:
    return PNG_MAGIC + b"\0" * (size - len(PNG_MAGIC))


def presign(s3, bucket: str, key: str, expires: int = 300) -> dict:
    return s3.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields={"Content-Type": "image/png"},
        Conditions=[
            {"Content-Type": "image/png"},
            ["content-length-range", 1, MAX_BYTES],
        ],
        ExpiresIn=expires,
    )


def upload(form: dict, body: bytes, *, override: dict | None = None, headers=None):
    fields = {**form["fields"], **(override or {})}
    # S3는 file 필드가 마지막이어야 합니다.
    parts = [*fields.items(), ("file", ("upload.png", body, "image/png"))]
    return http.request(
        "POST", form["url"], fields=parts, headers=headers, redirect=False, retries=False
    )


def error_code(resp) -> str:
    body = resp.data.decode(errors="replace")
    return body.split("<Code>")[1].split("</Code>")[0] if "<Code>" in body else ""


def test_s3_rejects_body_over_size_limit(s3, bucket, new_key):
    at_limit = upload(presign(s3, bucket, new_key()), png_bytes(MAX_BYTES))
    over_limit = upload(presign(s3, bucket, new_key()), png_bytes(MAX_BYTES + 1))

    assert at_limit.status == 204
    assert over_limit.status == 400
    assert error_code(over_limit) == "EntityTooLarge"


def test_s3_rejects_mismatched_content_type(s3, bucket, new_key):
    form = presign(s3, bucket, new_key())

    resp = upload(form, png_bytes(1024), override={"Content-Type": "image/jpeg"})

    assert resp.status == 403
    assert b"Policy Condition failed" in resp.data


def test_s3_rejects_expired_post(s3, bucket, new_key):
    form = presign(s3, bucket, new_key(), expires=1)
    time.sleep(3)

    resp = upload(form, png_bytes(1024))

    assert resp.status == 403
    assert b"Policy expired" in resp.data


def test_s3_cors_preflight_allows_frontend_origin(s3, bucket, new_key):
    url = presign(s3, bucket, new_key())["url"]

    def preflight(origin: str):
        return http.request(
            "OPTIONS",
            url,
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
            retries=False,
        )

    allowed = preflight(FRONTEND_ORIGIN)
    other = preflight("http://evil.example")

    assert allowed.status == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == FRONTEND_ORIGIN
    assert other.status == 403
    assert "Access-Control-Allow-Origin" not in other.headers


def test_s3_presigned_post_uses_regional_endpoint_and_succeeds(s3, bucket, new_key):
    form = presign(s3, bucket, new_key())

    resp = upload(form, png_bytes(1024), headers={"Origin": FRONTEND_ORIGIN})

    assert form["url"] == f"https://{bucket}.s3.{settings.AWS_REGION}.amazonaws.com/"
    assert resp.status == 204


def test_s3_object_is_not_publicly_readable(s3, bucket, new_key):
    key = new_key()
    assert upload(presign(s3, bucket, key), png_bytes(1024)).status == 204

    resp = http.request(
        "GET", f"https://{bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{key}", retries=False
    )

    assert resp.status == 403


def test_s3_head_missing_object_returns_404(s3, bucket, new_key):
    with pytest.raises(ClientError) as exc_info:
        s3.head_object(Bucket=bucket, Key=new_key())

    assert exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"] == 404
