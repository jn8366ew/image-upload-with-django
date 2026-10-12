variable "region" {
  description = "버킷 리전. boto3 클라이언트의 region_name과 같아야 합니다 (ADR-001)."
  type        = string
  default     = "ap-northeast-2"
}

variable "bucket_name" {
  description = "S3 버킷 이름 (전 세계 유일). terraform.tfvars에 지정합니다."
  type        = string
}

variable "budget_email" {
  description = "AWS Budgets 알림을 받을 이메일. terraform.tfvars에만 둡니다."
  type        = string
}

variable "frontend_origin" {
  description = "S3 CORS에서 허용할 프론트 origin (ADR-006)."
  type        = string
  default     = "http://localhost:5173"
}

variable "attachments_prefix" {
  description = "첨부 객체 key prefix (ADR-004: attachments/{user_id}/{uuid}.{ext})."
  type        = string
  default     = "attachments/"
}
