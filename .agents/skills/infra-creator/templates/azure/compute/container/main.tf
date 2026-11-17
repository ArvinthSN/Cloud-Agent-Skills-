resource "azurerm_log_analytics_workspace" "this" {
  name                = "${var.name_prefix}-logs"
  location            = var.location
  resource_group_name = split("/", var.subnet_id)[4]
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "this" {
  name                       = "${var.name_prefix}-cae"
  location                   = var.location
  resource_group_name        = split("/", var.subnet_id)[4]
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  infrastructure_subnet_id   = var.subnet_id
}

resource "azurerm_container_registry" "this" {
  name                = replace("${var.name_prefix}acr", "-", "")
  resource_group_name = split("/", var.subnet_id)[4]
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = true
}

resource "azurerm_container_app" "this" {
  name                         = "${var.name_prefix}-app"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = split("/", var.subnet_id)[4]
  revision_mode                = "Single"

  template {
    container {
      name   = "app"
      image  = "${azurerm_container_registry.this.login_server}/app:latest"
      cpu    = 0.5
      memory = "1Gi"
      env {
        name  = "PORT"
        value = tostring(var.container_port)
      }
    }
    min_replicas = var.environment == "prod" ? 2 : 1
    max_replicas = var.environment == "prod" ? 10 : 3
  }

  ingress {
    external_enabled = true
    target_port      = var.container_port
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}