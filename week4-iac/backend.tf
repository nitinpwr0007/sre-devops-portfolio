# REMOTE STATE: this stack stores its state in the S3 bucket + locks with the
# DynamoDB table the bootstrap stack created. The endpoints/skip_* block mirrors
# the provider so the backend also talks to LocalStack instead of real AWS.
#
# (Newer alternative to dynamodb_table: `use_lockfile = true` uses S3-native
# locking, no DynamoDB needed. We use DynamoDB here because that's the classic,
# still-most-common production pattern and the Week 4 D1 deliverable.)
terraform {
  backend "s3" {
    bucket = "tf-state"
    key    = "week4/vpc/terraform.tfstate"
    region = "us-east-1"

    access_key                  = "test"
    secret_key                  = "test"
    use_path_style              = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true

    endpoints = {
      s3       = "http://localhost:14566"
      dynamodb = "http://localhost:14566"
    }

    dynamodb_table = "tf-lock"
  }
}
