# D6 — the bucket was first created OUTSIDE Terraform and adopted via an import{}
# block (now removed — import is a one-time action). It is now renamed from
# "legacy" to "adopted" to demonstrate a safe refactor.
resource "aws_s3_bucket" "adopted" {
  bucket = "${var.name}-adopted"
}

# moved{} tells Terraform the resource at the old address IS the one now at the
# new address — it rewrites the state key in place. Without this, renaming a
# resource = destroy old + create new. With it: 0 to destroy, just a relabel.
moved {
  from = aws_s3_bucket.legacy
  to   = aws_s3_bucket.adopted
}

# Hardening so the trivy pre-commit gate (D5) passes: block all public access
# and enforce encryption at rest, same pattern as the bootstrap state bucket.
resource "aws_s3_bucket_public_access_block" "adopted" {
  bucket                  = aws_s3_bucket.adopted.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#trivy:ignore:AVD-AWS-0132 lab uses SSE-S3 (AES256); no KMS in LocalStack
resource "aws_s3_bucket_server_side_encryption_configuration" "adopted" {
  bucket = aws_s3_bucket.adopted.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
