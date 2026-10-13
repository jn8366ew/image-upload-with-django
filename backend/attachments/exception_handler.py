from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from attachments.exceptions import (
    AttachmentNotFound,
    NotOwner,
    UploadNotReceived,
    UploadRejected,
)


def handle_exception(exc, context):
    if isinstance(exc, UploadRejected):
        body = {"detail": exc.reason}
        if exc.client_ref is not None:
            body["client_ref"] = exc.client_ref
        return Response(body, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, NotOwner):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, AttachmentNotFound):
        return Response({"detail": "not_found"}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, UploadNotReceived):
        return Response({"detail": "object_missing"}, status=status.HTTP_409_CONFLICT)
    return exception_handler(exc, context)
