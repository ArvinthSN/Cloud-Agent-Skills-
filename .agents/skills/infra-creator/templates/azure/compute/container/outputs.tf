output "fqdn" { value = azurerm_container_app.this.ingress[0].fqdn }
output "container_app_id" { value = azurerm_container_app.this.id }
output "acr_login_server" { value = azurerm_container_registry.this.login_server }