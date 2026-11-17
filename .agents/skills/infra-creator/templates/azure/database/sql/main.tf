resource "azurerm_postgresql_flexible_server" "this" {
  name                   = "${var.name_prefix}-pg"
  resource_group_name    = split("/", var.subnet_id)[4]
  location               = var.location
  version                = "15"
  administrator_login    = var.db_username
  administrator_password = var.db_password
  storage_mb             = 32768
  sku_name               = var.environment == "prod" ? "GP_Standard_D2s_v3" : "B_Standard_B1ms"
  zone                   = "1"

  tags = { Environment = var.environment }
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = "appdb"
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "deny_public" {
  count            = 0
  name             = "deny-all-public"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}