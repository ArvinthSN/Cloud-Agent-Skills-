variable "name_prefix" { type = string }
variable "location" { type = string }
variable "environment" { type = string }
variable "subnet_id" { type = string }
variable "db_engine" {
  type = string
  default = "postgres"
}
variable "db_username" {
  type = string
  sensitive = true
}
variable "db_password" {
  type = string
  sensitive = true
}
variable "private_dns_zone_id" { type = string }
