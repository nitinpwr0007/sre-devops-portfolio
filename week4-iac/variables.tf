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
