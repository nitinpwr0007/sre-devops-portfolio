# for_each over a SET of subnet ids => one instance per subnet. Using toset()
# means each.key == each.value == the subnet id, so instances are keyed by
# subnet (aws_instance.this["subnet-0124c74b"]) instead of a fragile index.
resource "aws_instance" "this" {
  for_each = toset(var.subnet_ids)

  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = each.value
  vpc_security_group_ids = var.security_group_ids

  tags = { Name = "${var.name}-${each.key}" }
}
