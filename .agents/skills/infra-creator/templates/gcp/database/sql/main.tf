resource "google_sql_database_instance" "this" {
  name             = "${var.name_prefix}-sql"
  project          = var.project_id
  region           = var.region
  database_version = var.db_engine == "mysql" ? "MYSQL_8_0" : "POSTGRES_15"

  settings {
    tier = var.environment == "prod" ? "db-custom-2-7680" : "db-f1-micro"
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_id
    }
    backup_configuration {
      enabled = true
    }
    disk_size = 20
  }

  deletion_protection = var.environment == "prod"
}

resource "google_sql_database" "app" {
  name     = "appdb"
  project  = var.project_id
  instance = google_sql_database_instance.this.name
}

resource "google_sql_user" "app" {
  name     = var.db_username
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  password = var.db_password
}