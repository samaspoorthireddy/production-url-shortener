# Design Document: Event Processing Pipeline

Author: Jamie Chen
Date: March 15, 2025
Status: Proposed

## Problem Statement
Our application generates user activity events (page views, clicks, purchases) that we currently process synchronously during the API request. This adds 150-300ms of latency to every request. As traffic grows, this synchronous processing will become a bottleneck. We need to move event processing out of the request path to keep API response times fast.

## Proposed Approach
We will implement an asynchronous event processing pipeline using Apache Kafka.

Events will be published to Kafka topics during the API request. The publish operation takes <5ms, compared to the current 150-300ms of synchronous processing. Separate consumer services will read events from Kafka and process them independently.

### Architecture
1. API servers publish events to Kafka topics (one topic per event type).
2. Consumer services subscribe to topics and process events.
3. Processed results are written to the analytics database.
4. Failed events are retried up to 3 times, then sent to a dead letter queue for manual inspection.

### Implementation Plan
- Week 1-2: Set up Kafka cluster (3 brokers) and create topics.
- Week 3-4: Modify API to publish events asynchronously.
- Week 5-6: Build consumer services for each event type.
- Week 7: Integration testing and cutover.

## Alternatives Considered

### Alternative 1: Managed queue service (like AWS SQS)
AWS SQS is a fully managed message queuing service that handles queue provisioning, scaling, and message retries. Using SQS eliminates the operational overhead of setting up and operating self-hosted Kafka brokers, saving our team setup time. However, SQS introduces a cloud vendor dependency and per-message costs that could become high at scale, and it lacks Kafka's log-replay features.

### Alternative 2: In-process background worker queue (like Celery with Redis broker)
Celery is an application-level task queue that processes background jobs on dedicated worker processes using Redis for message transport. This option is simple to operate and leverages our existing Redis infrastructure, lowering deployment complexity. We are not recommending this because task payloads are stored in memory, risking data loss if the Redis server crashes under peak load.

## Risks and Mitigations

### Kafka cluster failure
If Kafka goes down, events will be lost. To mitigate this, we will configure a replication factor of 3 across brokers. Additionally, if the API gateway cannot publish to Kafka, the client library will queue up to 5,000 events in a local memory buffer. If the outage exceeds this buffer, the gateway will fail-open (dropping activity events) and fire a critical PagerDuty alert, prioritizing main API uptime over non-critical tracking.

### Consumer lag
If consumers fall behind, event processing will be delayed. To mitigate this, we will set up a Datadog alert to trigger when consumer lag exceeds 10,000 events on any topic for more than 5 minutes. If triggered, the on-call engineer will run the `scale-consumers.sh` script to provision two additional worker instances within 15 minutes. If lag does not recover within 15 minutes, they will escalate to the platform team lead.

### Data consistency
Events may be processed out of order. To guarantee chronological order without bottlenecks, we will partition topics by user ID. This ensures all events for a specific user are routed to the same partition and processed in order, while allowing us to run multiple consumer instances in parallel across different partitions.

## Open Questions
- **Analytics database write capacity:** Can the analytics database sustain 10K writes/second under production conditions? The current benchmark was run against unknown conditions. Before implementation begins, the database team should run a load test simulating the actual event schema, indexing pattern, and concurrent read load. If the database cannot handle the projected write volume, we may need to add a write-ahead buffer or switch to a time-series database for event storage.
- **Retention period:** How long should we retain events in the Kafka log before discarding them?
