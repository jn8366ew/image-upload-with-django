from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class PresignedPost:
    url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class StoredObject:
    stream: BinaryIO
    content_type: str


class StorageGateway(Protocol):
    def presign_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost: ...

    def head(self, key: str) -> str: ...

    def read_prefix(self, key: str) -> bytes: ...

    def open(self, key: str) -> StoredObject: ...

    def delete(self, key: str) -> None: ...
