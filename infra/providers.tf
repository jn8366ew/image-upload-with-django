provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "image-upload-with-django"
      ManagedBy = "terraform"
    }
  }
}
