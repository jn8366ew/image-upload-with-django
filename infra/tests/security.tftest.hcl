# 로드맵 0-2 보안·비용 설정 단언 (ADR-005, ADR-006, ADR-014)
# mock provider로 실행하므로 AWS 자격 증명이 필요 없습니다.
# Versioning 리소스 부재와 허용 리소스 타입은 scripts/check_resource_types.sh가 검사합니다.

mock_provider "aws" {}

# 버킷 ARN은 apply 뒤에 정해지므로, plan 단계에서 쓸 값을 고정합니다.
override_resource {
  target          = aws_s3_bucket.attachments
  override_during = plan
  values = {
    arn = "arn:aws:s3:::image-upload-test-bucket"
  }
}

variables {
  bucket_name  = "image-upload-test-bucket"
  budget_email = "test@example.com"
}

run "bucket_blocks_all_public_access" {
  command = plan

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.attachments.block_public_acls,
      aws_s3_bucket_public_access_block.attachments.block_public_policy,
      aws_s3_bucket_public_access_block.attachments.ignore_public_acls,
      aws_s3_bucket_public_access_block.attachments.restrict_public_buckets,
    ])
    error_message = "Block Public Access 4개 설정이 모두 켜져 있어야 합니다."
  }
}

run "bucket_policy_denies_insecure_transport" {
  command = plan

  assert {
    condition = anytrue([
      for s in data.aws_iam_policy_document.attachments_bucket.statement :
      s.effect == "Deny" && anytrue([
        for c in s.condition :
        c.test == "Bool" && c.variable == "aws:SecureTransport" && contains(c.values, "false")
      ])
    ])
    error_message = "버킷 정책에 aws:SecureTransport=false Deny가 있어야 합니다."
  }
}

run "bucket_acls_are_disabled" {
  command = plan

  assert {
    condition     = one(aws_s3_bucket_ownership_controls.attachments.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "ACL이 비활성(BucketOwnerEnforced)이어야 합니다."
  }
}

run "lifecycle_expires_attachments_and_aborts_multipart" {
  command = plan

  assert {
    condition = anytrue([
      for r in aws_s3_bucket_lifecycle_configuration.attachments.rule :
      r.status == "Enabled"
      && one(r.filter).prefix == "attachments/"
      && one(r.expiration).days == 370
    ])
    error_message = "prefix attachments/에 Expiration 370일 규칙이 있어야 합니다."
  }

  assert {
    condition = anytrue([
      for r in aws_s3_bucket_lifecycle_configuration.attachments.rule :
      r.status == "Enabled"
      && length(r.abort_incomplete_multipart_upload) == 1
      && one(r.abort_incomplete_multipart_upload).days_after_initiation == 1
    ])
    error_message = "AbortIncompleteMultipartUpload 1일 규칙이 있어야 합니다."
  }
}

run "cors_allows_only_frontend_origin_post" {
  command = plan

  assert {
    condition = alltrue([
      for r in aws_s3_bucket_cors_configuration.attachments.cors_rule :
      toset(r.allowed_origins) == toset(["http://localhost:5173"])
      && toset(r.allowed_methods) == toset(["POST"])
    ])
    error_message = "CORS는 origin http://localhost:5173, 메서드 POST만 허용해야 합니다."
  }
}

run "dev_user_limited_to_attachments_prefix" {
  command = plan

  assert {
    condition = alltrue([
      for s in data.aws_iam_policy_document.dev_attachments.statement :
      s.effect == "Allow"
      && toset(s.actions) == toset(["s3:PutObject", "s3:GetObject", "s3:DeleteObject"])
      && alltrue([for r in s.resources : endswith(r, "/attachments/*")])
    ])
    error_message = "dev IAM 권한은 버킷 attachments/ prefix의 PutObject·GetObject·DeleteObject로 한정되어야 합니다."
  }
}

run "bucket_uses_sse_s3_not_kms" {
  command = plan

  # AES256은 SSE-S3입니다. KMS를 쓰려면 aws:kms 계열 알고리즘이어야 하므로 이것으로 KMS 미사용도 보장됩니다.
  assert {
    condition = alltrue([
      for r in aws_s3_bucket_server_side_encryption_configuration.attachments.rule :
      one(r.apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    ])
    error_message = "버킷 암호화는 SSE-S3(AES256)여야 하며 KMS 키를 쓰지 않아야 합니다."
  }
}

run "budget_alerts_at_1_and_3_dollars" {
  command = plan

  assert {
    condition = toset([
      for n in aws_budgets_budget.monthly.notification :
      "${n.notification_type}:${n.threshold}:${n.threshold_type}"
      ]) == toset([
      "ACTUAL:1:ABSOLUTE_VALUE",
      "ACTUAL:3:ABSOLUTE_VALUE",
      "FORECASTED:3:ABSOLUTE_VALUE",
    ])
    error_message = "Budgets 알림은 실제 $1·$3, 예측 $3이어야 합니다."
  }

  assert {
    condition = alltrue([
      for n in aws_budgets_budget.monthly.notification :
      contains(n.subscriber_email_addresses, var.budget_email)
    ])
    error_message = "모든 Budgets 알림이 budget_email로 가야 합니다."
  }
}
