import base64
import json

import pytest

from attachments.exceptions import ObjectNotFound, StorageError

KEY = "attachments/1/abc.png"
MAX_BYTES = 2_621_440


def decode_policy(fields: dict[str, str]) -> dict:
    return json.loads(base64.b64decode(fields["policy"]))


def test_presign_post_returns_url_and_fields(store):
    form = store.gateway.presign_post(
        KEY, content_type="image/png", max_bytes=MAX_BYTES, expires_in=300
    )

    assert form.url == f"https://{store.bucket}.s3.ap-northeast-2.amazonaws.com/"
    assert form.fields["key"] == KEY
    assert form.fields["Content-Type"] == "image/png"
    conditions = decode_policy(form.fields)["conditions"]
    assert {"key": KEY} in conditions
    assert {"Content-Type": "image/png"} in conditions
    assert ["content-length-range", 1, MAX_BYTES] in conditions


def test_head_missing_key_raises_object_not_found(store):
    store.put(KEY, b"data", "image/png")
    store.gateway.head(KEY)

    with pytest.raises(ObjectNotFound):
        store.gateway.head("attachments/1/missing.png")


def test_read_prefix_requests_range_0_7(store):
    body = b"\x89PNG\r\n\x1a\n" + b"rest-of-image"
    store.put(KEY, body, "image/png")

    assert store.gateway.read_prefix(KEY) == body[:8]
    if store.sent_ranges is not None:
        assert store.sent_ranges == ["bytes=0-7"]


def test_open_returns_stream_and_content_type(store):
    store.put(KEY, b"jpeg-bytes", "image/jpeg")

    obj = store.gateway.open(KEY)

    assert obj.stream.read() == b"jpeg-bytes"
    assert obj.content_type == "image/jpeg"


def test_open_missing_key_raises_object_not_found(store):
    with pytest.raises(ObjectNotFound):
        store.gateway.open("attachments/1/missing.png")


def test_delete_missing_key_succeeds(store):
    store.put(KEY, b"data", "image/png")

    store.gateway.delete(KEY)
    store.gateway.delete(KEY)

    with pytest.raises(ObjectNotFound):
        store.gateway.head(KEY)


def test_delete_failure_raises_storage_error(store):
    store.put(KEY, b"data", "image/png")
    store.fail_delete(KEY)

    with pytest.raises(StorageError):
        store.gateway.delete(KEY)
