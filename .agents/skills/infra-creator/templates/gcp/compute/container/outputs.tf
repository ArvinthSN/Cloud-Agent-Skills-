output "service_url" { value = google_cloud_run_v2_service.this.uri }
output "service_name" { value = google_cloud_run_v2_service.this.name }
output "artifact_registry" { value = google_artifact_registry_repository.this.name }