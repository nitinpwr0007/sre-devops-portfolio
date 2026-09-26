# for_each over the map => one SG per entry, addressed as
# aws_security_group.this["web"], ["app"], ... (stable keys, unlike count's
# positional indexes). each.key = the map key, each.value = the object.
resource "aws_security_group" "this" {
  for_each = var.security_groups

  name        = "${var.name}-${each.key}"
  description = each.value.description
  vpc_id      = var.vpc_id

  # dynamic block = generate one ingress {} per rule in the list without
  # copy-pasting. ingress.value is each element of each.value.ingress.
  dynamic "ingress" {
    for_each = each.value.ingress
    content {
      from_port   = ingress.value.from_port
      to_port     = ingress.value.to_port
      protocol    = ingress.value.protocol
      cidr_blocks = ingress.value.cidr_blocks
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1" # all protocols
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-${each.key}" }
}
