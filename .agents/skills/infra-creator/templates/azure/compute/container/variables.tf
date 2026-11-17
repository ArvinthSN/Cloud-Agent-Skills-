variable "name_prefix" { type = string }
variable "location" { type = string }
variable "environment" { type = string }
variable "subnet_id" { type = string }
variable "container_port" { type = number; default = 8000 }