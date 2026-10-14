import pytest
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from attachments.exceptions import StorageAuthError, StorageError
from attachments.storage.s3 import build_s3_gateway

AUTH_CODES = [
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
]


def client_error(code):
    return ClientError({"Error": {"Code": code, "Message": code}}, "DeleteObject")


def gateway_raising(error):
    gateway = build_s3_gateway()

    def fail(**_):
        raise error

    gateway._client.delete_object = fail
    return gateway


@pytest.mark.parametrize(
    "error",
    [
        *[client_error(code) for code in AUTH_CODES],
        NoCredentialsError(),
        PartialCredentialsError(provider="env", cred_var="AWS_SECRET_ACCESS_KEY"),
    ],
    ids=[*AUTH_CODES, "NoCredentialsError", "PartialCredentialsError"],
)
def test_s3_error_codes_map_to_auth_or_transient(aws, error):
    with pytest.raises(StorageAuthError):
        gateway_raising(error).delete("attachments/1/abc.png")


@pytest.mark.parametrize("code", ["RequestTimeout", "InternalError"])
def test_s3_transient_error_codes_stay_storage_error(aws, code):
    with pytest.raises(StorageError) as exc:
        gateway_raising(client_error(code)).delete("attachments/1/abc.png")

    assert type(exc.value) is StorageError
