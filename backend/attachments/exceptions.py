"""도메인 예외. 모든 계층이 import할 수 있습니다 (ADR-015).

HTTP 상태 매핑은 DRF 커스텀 EXCEPTION_HANDLER 한 곳에서만 합니다.
"""


class DomainError(Exception):
    """모든 도메인 예외의 기반 클래스."""


class ObjectNotFound(DomainError):
    pass


class StorageError(DomainError):
    pass


class StorageAuthError(StorageError):
    """재시도해도 해결되지 않는 인증·권한·설정 오류."""


class UploadRejected(DomainError):
    def __init__(self, reason: str, client_ref: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.client_ref = client_ref


class NotOwner(DomainError):
    pass


class AttachmentNotFound(DomainError):
    pass


class UploadNotReceived(DomainError):
    pass
