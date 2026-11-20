variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids" { type = list(string) }
variable "container_port" {
  type = number
  default = 8000
}
variable "desired_count" {
  type = number
  default = 2
}
variable "task_cpu" {
  type = number
  default = 256
}
variable "task_memory" {
  type = number
  default = 512
}
variable "health_check_path" {
  type = string
  default = "/health"
}
variable "container_image" { type = string }
variable "certificate_arn" { type = string }
