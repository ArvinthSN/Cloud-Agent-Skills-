output "endpoint" {
  value     = google_sql_database_instance.this.private_ip_address
  sensitive = true
}
output "connection_name" { value = google_sql_database_instance.this.connection_name }