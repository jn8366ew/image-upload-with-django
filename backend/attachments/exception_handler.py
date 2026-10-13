from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from attachments.exceptions import UploadRejected


def handle_exception(exc, context):
    if isinstance(exc, UploadRejected):
        return Response(
            {"detail": exc.reason, "client_ref": exc.client_ref},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return exception_handler(exc, context)
