# Root stack = just a thin caller of the reusable VPC module. Everything about
# HOW a VPC is built lives in modules/vpc; this file only supplies the inputs.
module "vpc" {
  source = "./modules/vpc"

  name                = var.name
  cidr_block          = var.cidr_block
  public_subnet_cidrs = var.public_subnet_cidrs
  azs                 = var.azs
}
