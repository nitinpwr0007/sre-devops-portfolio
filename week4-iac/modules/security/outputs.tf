# Return a map of {sg_name => sg_id} built by iterating the for_each resources.
output "security_group_ids" {
  description = "Map of security group name => id"
  value       = { for key, sg in aws_security_group.this : key => sg.id }
}
