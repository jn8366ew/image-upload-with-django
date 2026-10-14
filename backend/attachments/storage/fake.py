import base64
import io
import json

from attachments.exceptions import ObjectNotFound, StorageAuthError, StorageError
from attachments.storage.gateway import PresignedPost, StoredObject


class InMemoryStorageGateway:
    def __init__(self, bucket: str = "fake-bucket") -> None:
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_delete_for: set[str] = set()
        self.fail_head_for: set[str] = set()
        self.auth_broken = False

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = (body, content_type)

    def presign_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost:
        conditions = [
            {"key": key},
            {"Content-Type": content_type},
            ["content-length-range", 1, max_bytes],
        ]
        policy = base64.b64encode(json.dumps({"conditions": conditions}).encode()).decode()
        return PresignedPost(
            url=f"https://{self.bucket}.s3.ap-northeast-2.amazonaws.com/",
            fields={"key": key, "Content-Type": content_type, "policy": policy},
        )

    def head(self, key: str) -> str:
        if self.auth_broken:
            raise StorageAuthError(key)
        if key in self.fail_head_for:
            raise StorageError(key)
        if key not in self.objects:
            raise ObjectNotFound(key)
        return self.objects[key][1]

    def read_prefix(self, key: str) -> bytes:
        return self.objects[key][0][:8]

    def open(self, key: str) -> StoredObject:
        self.head(key)
        body, content_type = self.objects[key]
        return StoredObject(stream=io.BytesIO(body), content_type=content_type)

    def delete(self, key: str) -> None:
        if self.auth_broken:
            raise StorageAuthError(key)
        if key in self.fail_delete_for:
            raise StorageError(key)
        self.objects.pop(key, None)
