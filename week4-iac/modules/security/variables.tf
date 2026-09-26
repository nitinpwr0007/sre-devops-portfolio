variable "name" {
  description = "Name prefix for tagging"
  type        = string
}

variable "vpc_id" {
  description = "VPC the security groups belong to"
  type        = string
}

# A MAP of security groups. The key (e.g. \"web\") becomes each SG's name suffix,
# and for_each turns each entry into its own aws_security_group resource.
variable "security_groups" {
  description = "Map of security groups to create, each with its ingress rules"
  type = map(object({
    description = string
    ingress = list(object({
      from_port   = number
      to_port     = number
      protocol    = string
      cidr_blocks = list(string)
    }))
  }))
}
