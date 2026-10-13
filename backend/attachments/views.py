from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from attachments.serializers import PresignRequestSerializer
from attachments.services.uploads import UploadRequest, presign_uploads
from attachments.storage.s3 import build_s3_gateway


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
