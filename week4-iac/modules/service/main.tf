# for_each over a MAP with static keys (the AZ). each.key is known at plan time
# so Terraform can name the instances; each.value (subnet id) may be unknown
# until apply, which for_each allows for VALUES but not keys.
resource "aws_instance" "this" {
  for_each = var.subnet_ids

  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = each.value
  vpc_security_group_ids = var.security_group_ids

  tags = { Name = "${var.name}-${each.key}" }
}
