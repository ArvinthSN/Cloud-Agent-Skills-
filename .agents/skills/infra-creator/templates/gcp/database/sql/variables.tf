variable "name_prefix" { type = string }
variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "network_id" { type = string }
variable "db_engine" { type = string; default = "postgres" }
variable "db_username" { type = string; sensitive = true }
variable "db_password" { type = string; sensitive = true }