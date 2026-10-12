# 이미지 저장 버킷 (ADR-005, ADR-006, ADR-014)
#
# Versioning 리소스는 의도적으로 두지 않습니다. 한 번 켜면 Disabled로 되돌릴 수 없고,
# 켜져 있으면 삭제가 delete marker만 남겨 하드 삭제가 되지 않습니다 (ADR-005).
resource "aws_s3_bucket" "attachments" {
  #checkov:skip=CKV_AWS_21:Versioning을 끄는 것이 하드 삭제 요건입니다 (ADR-005).
  #checkov:skip=CKV_AWS_145:KMS 고객 관리형 키는 비용 때문에 쓰지 않고 SSE-S3를 씁니다 (ADR-014).
  #checkov:skip=CKV_AWS_18:Access logging 버킷은 MVP 범위 밖입니다. 접근 로그는 Django가 남깁니다 (ADR-012).
  #checkov:skip=CKV_AWS_144:Cross-region replication은 MVP 범위 밖입니다 (ADR-014).
  #checkov:skip=CKV2_AWS_62:S3 이벤트 알림을 쓰지 않습니다 (ADR-003).
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "attachments_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.attachments.arn,
      "${aws_s3_bucket.attachments.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  policy = data.aws_iam_policy_document.attachments_bucket.json

  # BPA가 먼저 적용된 뒤 정책을 붙입니다.
  depends_on = [aws_s3_bucket_public_access_block.attachments]
}

resource "aws_s3_bucket_lifecycle_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  # 배치가 놓친 고아 객체를 지우는 안전망 (ADR-005)
  rule {
    id     = "expire-attachments"
    status = "Enabled"

    filter {
      prefix = var.attachments_prefix
    }

    expiration {
      days = 370
    }
  }

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  # presigned POST 업로드만 허용합니다. 읽기는 Django 경유입니다 (ADR-012).
  cors_rule {
    allowed_origins = [var.frontend_origin]
    allowed_methods = ["POST"]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}
