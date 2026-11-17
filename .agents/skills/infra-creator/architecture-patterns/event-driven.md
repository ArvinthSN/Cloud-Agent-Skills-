# Event-Driven Architecture

Producers and consumers communicate via events/brokers.

**Detection:** Kafka, RabbitMQ, SQS, SNS, Pub/Sub, Service Bus, Celery, workers/queues.

| Cloud | Broker | Consumers |
|-------|--------|-----------|
| AWS | SQS/SNS/EventBridge/MSK | Lambda / ECS |
| Azure | Service Bus / Event Grid | Functions / Container Apps |
| GCP | Pub/Sub | Cloud Run / Functions |