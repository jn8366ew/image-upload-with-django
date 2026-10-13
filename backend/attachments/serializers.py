from rest_framework import serializers


def reject_control_characters(value: str) -> None:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise serializers.ValidationError("control characters are not allowed")


class UploadRequestSerializer(serializers.Serializer):
    client_ref = serializers.CharField(max_length=64)
    filename = serializers.CharField(max_length=255, validators=[reject_control_characters])
    content_type = serializers.CharField()
    size = serializers.IntegerField(min_value=1)


class PresignRequestSerializer(serializers.Serializer):
    files = UploadRequestSerializer(many=True, allow_empty=False)


class AttachmentListItemSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    original_filename = serializers.CharField()
    uploaded_at = serializers.DateTimeField()
