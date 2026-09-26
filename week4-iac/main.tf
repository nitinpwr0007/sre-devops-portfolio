# Root stack = just a thin caller of the reusable VPC module. Everything about
# HOW a VPC is built lives in modules/vpc; this file only supplies the inputs.
module "vpc" {
  source = "./modules/vpc"

  name                = var.name
  cidr_block          = var.cidr_block
  public_subnet_cidrs = var.public_subnet_cidrs
  azs                 = var.azs
}

# SG module: driven by a map var + for_each. Depends on vpc for the vpc_id.
module "security" {
  source = "./modules/security"

  name            = var.name
  vpc_id          = module.vpc.vpc_id
  security_groups = var.security_groups
}

# Service module: one EC2 instance per public subnet (for_each). Takes the
# subnet ids from vpc and the SG ids from security -> module composition.
module "service" {
  source = "./modules/service"

  name               = var.name
  ami_id             = var.ami_id
  instance_type      = var.instance_type
  subnet_ids         = module.vpc.public_subnet_ids
  security_group_ids = [for id in module.security.security_group_ids : id]
}
