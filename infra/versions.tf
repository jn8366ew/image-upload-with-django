terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # state는 로컬 파일로 둡니다 (ADR-014, gitignore).
}
