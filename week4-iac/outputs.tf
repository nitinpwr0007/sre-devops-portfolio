output "vpc_id" {
  description = "ID of the created VPC"
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = module.vpc.public_subnet_ids
}

output "igw_id" {
  description = "ID of the internet gateway"
  value       = module.vpc.igw_id
}

output "security_group_ids" {
  description = "Map of security group name => id"
  value       = module.security.security_group_ids
}

output "instance_ids" {
  description = "Map of subnet id => EC2 instance id"
  value       = module.service.instance_ids
}
