variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "db_engine" { type = string; default = "postgres" }
variable "db_instance_class" { type = string; default = "db.t3.micro" }
variable "db_name" { type = string; default = "appdb" }
variable "db_username" { type = string; sensitive = true }
variable "db_password" { type = string; sensitive = true }
variable "db_port" { type = number; default = 5432 }
variable "allowed_security_group_ids" { type = list(string); default = [] }