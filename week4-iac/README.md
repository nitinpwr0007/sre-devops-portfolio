# week4-iac — Terraform on LocalStack (no AWS account, $0)

Real Terraform + AWS provider workflow against **LocalStack**, a local AWS
emulator. Everything runs on Docker/colima — no signup, no credit card, no cost.

## Layout
```
docker-compose.yml     LocalStack (S3, DynamoDB, EC2, IAM, STS on :14566)
bootstrap/             one-time: creates the S3 state bucket + DynamoDB lock table
providers.tf           AWS provider pointed at LocalStack
backend.tf             S3 remote state + DynamoDB locking
main.tf                calls the VPC module
variables.tf outputs.tf
modules/vpc/           reusable VPC module (vpc + public subnets + IGW + routes)
```

## D1 — Remote state (S3 + DynamoDB lock) + VPC module

```bash
# 0. start LocalStack
docker compose up -d
curl -s localhost:14566/_localstack/health | jq .   # s3/dynamodb/ec2 = available

# 1. bootstrap the backend (local state creates the bucket + lock table)
cd bootstrap
terraform init
terraform apply -auto-approve
cd ..

# 2. the real stack: uses the S3 backend + DynamoDB lock, builds the VPC
terraform init      # initializes the S3 backend against LocalStack
terraform plan
terraform apply -auto-approve
terraform output    # vpc_id, public_subnet_ids, igw_id
```

### Verify it landed in LocalStack
```bash
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
alias awslocal='aws --endpoint-url=http://localhost:14566'
awslocal s3 ls s3://tf-state --recursive        # the remote state object
awslocal dynamodb scan --table-name tf-lock      # lock rows (empty when idle)
awslocal ec2 describe-vpcs --query 'Vpcs[].VpcId'
awslocal ec2 describe-subnets --query 'Subnets[].SubnetId'
```

### Teardown
```bash
terraform destroy -auto-approve          # remove the VPC
docker compose down                      # stop LocalStack
# NOTE: LocalStack state is in-memory; `compose down` wipes the bucket/table too,
# so after a restart re-run the bootstrap step before the root stack.
```

## Notes
- `dynamodb_table` in the backend = classic DynamoDB state locking. Newer
  Terraform (1.10+) also supports `use_lockfile = true` for S3-native locking.
- `.terraform.lock.hcl` (provider version lock) SHOULD be committed; `.terraform/`
  and `*.tfstate*` are gitignored.

