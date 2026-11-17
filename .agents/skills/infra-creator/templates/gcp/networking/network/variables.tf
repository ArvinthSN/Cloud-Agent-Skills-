variable "name_prefix" { type = string }
variable "project_id" { type = string }
variable "region" { type = string }
variable "network_cidr" { type = string; default = "10.0.0.0/16" }
variable "environment" { type = string; default = "dev" }