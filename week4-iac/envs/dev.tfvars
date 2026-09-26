# DEV environment — small + cheap. Same modules as prod, just different values.
name                = "dev"
cidr_block          = "10.10.0.0/16"
public_subnet_cidrs = ["10.10.1.0/24", "10.10.2.0/24"]
azs                 = ["us-east-1a", "us-east-1b"]
instance_type       = "t3.micro"

# dev only needs a web SG
security_groups = {
  web = {
    description = "Allow HTTP from anywhere (dev)"
    ingress = [
      { from_port = 80, to_port = 80, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] },
      # SSH from inside the VPC only (bastion) — adopted from an out-of-band change (D4 drift drill)
      { from_port = 22, to_port = 22, protocol = "tcp", cidr_blocks = ["10.10.0.0/16"] },
    ]
  }
}
