output "bucket_name" {
  description = ".env의 S3_BUCKET에 넣을 값"
  value       = aws_s3_bucket.attachments.bucket
}

output "region" {
  description = ".env의 AWS_REGION에 넣을 값"
  value       = var.region
}

output "dev_user_name" {
  description = "액세스 키를 발급할 로컬 개발용 IAM 사용자"
  value       = aws_iam_user.dev.name
}
