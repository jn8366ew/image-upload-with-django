# 로컬 개발용 IAM 사용자 (ADR-006, ADR-014)
#
# 액세스 키는 Terraform으로 만들지 않습니다. 만들면 비밀 키가 tfstate에 평문으로 남습니다.
# apply 후 사용자가 직접 발급해 ~/.aws 프로파일에 둡니다.
resource "aws_iam_user" "dev" {
  #checkov:skip=CKV_AWS_273:로컬 Django가 쓸 최소 권한 자격 증명입니다. 사람 로그인은 SSO로 합니다 (ADR-014).
  name = "image-upload-dev"
}

data "aws_iam_policy_document" "dev_attachments" {
  statement {
    sid    = "AttachmentsObjectAccess"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.attachments.arn}/${var.attachments_prefix}*"]
  }

  # ListBucket이 없으면 없는 객체에 HeadObject가 404 대신 403을 받아,
  # /complete의 "객체 없음(409)"과 권한 오류를 구분할 수 없습니다 (0-3 spike, ADR-003).
  statement {
    sid       = "AttachmentsPrefixList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.attachments.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.attachments_prefix}*"]
    }
  }
}

resource "aws_iam_user_policy" "dev_attachments" {
  #checkov:skip=CKV_AWS_40:로컬 개발용 단일 사용자라 그룹 없이 인라인 정책 하나만 둡니다 (ADR-014).
  name   = "attachments-object-access"
  user   = aws_iam_user.dev.name
  policy = data.aws_iam_policy_document.dev_attachments.json
}
