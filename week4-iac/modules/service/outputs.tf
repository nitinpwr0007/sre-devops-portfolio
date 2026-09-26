output "instance_ids" {
  description = "Map of subnet id => instance id"
  value       = { for key, inst in aws_instance.this : key => inst.id }
}

output "private_ips" {
  description = "Map of subnet id => private IP"
  value       = { for key, inst in aws_instance.this : key => inst.private_ip }
}
