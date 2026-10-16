from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from attachments.client_ip import client_ip
from attachments.selectors.attachments import list_user_attachments
from attachments.serializers import AttachmentListItemSerializer, PresignRequestSerializer
from attachments.services.completion import complete_upload
from attachments.services.deletion import soft_delete
from attachments.services.downloads import open_download
from attachments.services.uploads import UploadRequest, presign_uploads
from attachments.storage.s3 import build_s3_gateway


def _client(request) -> dict[str, str | None]:
    return {
        "ip": client_ip(request.META, trusted_hops=settings.TRUSTED_PROXY_HOPS),
        "user_agent": request.META.get("HTTP_USER_AGENT"),
    }


class PresignView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "presign"

    def post(self, request):
        serializer = PresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploads = presign_uploads(
            request.user,
            [UploadRequest(**f) for f in serializer.validated_data["files"]],
            gateway=build_s3_gateway(),
        )
        return Response(
            {
                "uploads": [
                    {
                        "client_ref": u.client_ref,
                        "public_id": str(u.public_id),
                        "url": u.url,
                        "fields": u.fields,
                    }
                    for u in uploads
                ]
            },
            status=status.HTTP_201_CREATED,
        )


class CompleteView(APIView):
    def post(self, request, public_id):
        attachment = complete_upload(
            request.user, public_id, gateway=build_s3_gateway(), **_client(request)
        )
        return Response({"public_id": str(attachment.public_id), "status": attachment.status})


class AttachmentCursorPagination(CursorPagination):
    page_size = 50
    ordering = ("-uploaded_at", "-id")


class AttachmentListView(APIView):
    def get(self, request):
        paginator = AttachmentCursorPagination()
        page = paginator.paginate_queryset(list_user_attachments(request.user), request, self)
        return paginator.get_paginated_response(AttachmentListItemSerializer(page, many=True).data)


class AttachmentDetailView(APIView):
    def delete(self, request, public_id):
        soft_delete(request.user, public_id, **_client(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class DownloadView(APIView):
    def get(self, request, public_id):
        download = open_download(
            request.user, public_id, gateway=build_s3_gateway(), **_client(request)
        )
        response = FileResponse(
            download.stored.stream,
            as_attachment=True,
            filename=download.attachment.original_filename,
            content_type=download.stored.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
