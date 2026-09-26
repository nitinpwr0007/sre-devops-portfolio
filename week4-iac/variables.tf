variable "name" {
  description = "Name prefix applied to all resources"
  type        = string
  default     = "week4"
}

variable "cidr_block" {
  description = "CIDR range for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR for each public subnet (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "azs" {
  description = "Availability zones to spread the subnets across"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# Map of security groups -> passed straight into the security module's for_each.
variable "security_groups" {
  description = "Security groups to create (name => rules)"
  type = map(object({
    description = string
    ingress = list(object({
      from_port   = number
      to_port     = number
      protocol    = string
      cidr_blocks = list(string)
    }))
  }))
  default = {
    web = {
      description = "Allow HTTP/HTTPS from anywhere"
      ingress = [
        { from_port = 80, to_port = 80, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] },
        { from_port = 443, to_port = 443, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] },
      ]
    }
    app = {
      description = "Allow app port from inside the VPC only"
      ingress = [
        { from_port = 8080, to_port = 8080, protocol = "tcp", cidr_blocks = ["10.0.0.0/16"] },
      ]
    }
  }
}

variable "ami_id" {
  description = "AMI for the service instances (placeholder; LocalStack mocks EC2)"
  type        = string
  default     = "ami-0c55b159cbfafe1f0"
}

variable "instance_type" {
  description = "EC2 instance type for the service"
  type        = string
  default     = "t3.micro"
}
