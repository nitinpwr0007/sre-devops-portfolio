variable "name" {
  description = "Name prefix for tagging"
  type        = string
}

variable "subnet_ids" {
  description = "Map of stable key (e.g. AZ) => subnet id; one instance per entry"
  type        = map(string)
}

variable "security_group_ids" {
  description = "Security groups to attach to each instance"
  type        = list(string)
}

variable "ami_id" {
  description = "AMI to launch (a placeholder value; LocalStack mocks EC2)"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}
