# Microservices Architecture

Independently deployable services with own data and network communication.

**Detection:** multiple service dirs with Dockerfiles/deps, docker-compose with multiple app services, services/apps top-level. Folders alone are not enough.

**Infra:** shared network, per-service containers, optional per-service DB, messaging when async.

| Cloud | Compute | Messaging |
|-------|---------|-----------|
| AWS | ECS services + ALB | SQS/SNS/EventBridge |
| Azure | Container Apps | Service Bus |
| GCP | Cloud Run services | Pub/Sub |