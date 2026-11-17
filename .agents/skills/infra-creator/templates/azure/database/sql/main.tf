resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "${var.name_prefix}-pg"
  resource_group_name           = split("/", var.subnet_id)[4]
  location                      = var.location
  version                       = "15"
  administrator_login           = var.db_username
  administrator_password        = var.db_password
  storage_mb                    = 32768
  sku_name                      = var.environment == "prod" ? "GP_Standard_D2s_v3" : "B_Standard_B1ms"
  zone                          = "1"
  delegated_subnet_id           = var.subnet_id
  private_dns_zone_id           = var.private_dns_zone_id
  public_network_access_enabled = false

  tags = { Environment = var.environment }
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = "appdb"
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}
