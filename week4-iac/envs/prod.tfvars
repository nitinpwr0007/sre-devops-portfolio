# PROD environment — bigger: 3 AZs, larger instances, web + app SGs.
name                = "prod"
cidr_block          = "10.20.0.0/16"
public_subnet_cidrs = ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]
azs                 = ["us-east-1a", "us-east-1b", "us-east-1c"]
instance_type       = "t3.large"

security_groups = {
  web = {
    description = "Allow HTTP/HTTPS from anywhere (prod)"
    ingress = [
      { from_port = 80, to_port = 80, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] },
      { from_port = 443, to_port = 443, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] },
    ]
  }
  app = {
    description = "Allow app port from inside the VPC only (prod)"
    ingress = [
      { from_port = 8080, to_port = 8080, protocol = "tcp", cidr_blocks = ["10.20.0.0/16"] },
    ]
  }
}
