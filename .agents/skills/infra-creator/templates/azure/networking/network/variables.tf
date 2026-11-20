variable "name_prefix" { type = string }
variable "location" { type = string }
variable "vnet_cidr" {
  type = string
  default = "10.0.0.0/16"
}
variable "environment" {
  type = string
  default = "dev"
}