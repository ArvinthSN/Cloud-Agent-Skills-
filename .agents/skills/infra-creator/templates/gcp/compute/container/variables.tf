variable "name_prefix" { type = string }
variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "network_id" { type = string }
variable "subnet_id" { type = string }
variable "container_port" { type = number; default = 8000 }