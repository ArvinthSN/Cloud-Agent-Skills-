variable "name_prefix" { type = string }
variable "vpc_cidr" { type = string; default = "10.0.0.0/16" }
variable "environment" { type = string; default = "dev" }
variable "enable_nat_gateway" { type = bool; default = true }