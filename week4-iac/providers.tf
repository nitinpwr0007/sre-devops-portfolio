terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Same LocalStack wiring as the bootstrap stack, with the extra services the VPC
# module touches (ec2 for vpc/subnets/igw/route-tables).
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3       = "http://localhost:14566"
    dynamodb = "http://localhost:14566"
    ec2      = "http://localhost:14566"
    iam      = "http://localhost:14566"
    sts      = "http://localhost:14566"
  }
}
