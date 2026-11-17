output "endpoint" {
  value     = "${azurerm_postgresql_flexible_server.this.fqdn}:5432"
  sensitive = true
}
output "server_id" { value = azurerm_postgresql_flexible_server.this.id }