variable "name" {
  description = "Name prefix for tagging"
  type        = string
}

variable "cidr_block" {
  description = "CIDR range for the VPC"
  type        = string
}

variable "public_subnet_cidrs" {
  description = "CIDR for each public subnet"
  type        = list(string)
}

variable "azs" {
  description = "AZ for each public subnet (indexes must line up with public_subnet_cidrs)"
  type        = list(string)
}
