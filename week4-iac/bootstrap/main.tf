# The chicken-and-egg fix: you can't store Terraform state in an S3 bucket that
# doesn't exist yet. So this tiny stack uses a LOCAL backend (state file right
# here) to create the bucket + lock table that the REAL stack (../) then uses as
# its remote backend. You run this once, first.

resource "aws_s3_bucket" "state" {
  bucket = "tf-state"
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
