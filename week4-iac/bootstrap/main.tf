# The chicken-and-egg fix: you can't store Terraform state in an S3 bucket that
# doesn't exist yet. So this tiny stack uses a LOCAL backend (state file right
# here) to create the bucket + lock table that the REAL stack (../) then uses as
# its remote backend. You run this once, first.

resource "aws_s3_bucket" "state" {
  bucket = "tf-state"
}

# Block ALL public access — the state bucket holds infra secrets, never public.
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Encrypt state objects at rest. CMK ignore: LocalStack SERVICES has no KMS, so
# SSE-S3 (AES256) is used instead of a customer-managed key.
#trivy:ignore:AVD-AWS-0132
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning = keep a history of every state file, so a bad apply is recoverable.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# DynamoDB table for STATE LOCKING: while one apply holds the lock, a second
# `terraform apply` is blocked instead of corrupting shared state.
resource "aws_dynamodb_table" "lock" {
  name         = "tf-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID" # exact attribute name the S3 backend requires

  attribute {
    name = "LockID"
    type = "S"
  }
}
