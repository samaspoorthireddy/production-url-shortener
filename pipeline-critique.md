# Design Document Critique: Event Processing Pipeline

I have reviewed Jamie Chen's proposed *Event Processing Pipeline* design document and identified the three most dangerous gaps that could cause significant operational and engineering issues.

---

## 1. Missing "Alternatives Considered" Section (High Operational Complexity)

### What is the gap?
The document proposes using Apache Kafka without considering or comparing alternative message queuing or streaming options.

### What could go wrong?
Operating and managing a self-hosted, 3-broker Kafka cluster introduces massive operational complexity. For a small team of 3 engineers on a tight 7-week timeline, the overhead of provisioning, replication, partitions, cluster health monitoring, and managing dependency configurations will likely consume the majority of their capacity. Without evaluating simpler, lower-maintenance alternatives (such as AWS SQS, RabbitMQ, or Redis streams), the team may be taking on excessive, unneeded infrastructure overhead for a peak traffic load of only 2,000 events/second.

---

## 2. Horizontal Scaling Bottleneck (Data Consistency / Single Partition)

### What is the gap?
To guarantee order for sensitive events like purchases, the document states: *"we will use a single partition to guarantee ordering."*

### What could go wrong?
In Kafka, only a single consumer thread/instance can read from a single partition at any given time. Restricting all purchase events to a single partition locks the consumer scalability to exactly **one instance**. If purchase traffic spikes or processing slows down, this single consumer will become a bottleneck. We cannot scale the consumers horizontally to handle the backlog, resulting in severe consumer lag that could delay order fulfillment and billing.

---

## 3. Vague and Unactionable Risk Mitigations

### What is the gap?
The mitigation for consumer lag is to *"monitor consumer lag closely and scale up consumers if needed."*

### What could go wrong?
This is a statement of intent, not a mitigation plan. An on-call engineer waking up to an alert at 3 AM will not know what metrics define "falling behind," what thresholds trigger alerts, or what specific procedures to follow to scale the consumers. Additionally, because of the single partition restriction on purchase events (described in Gap 2), scaling up consumers for purchases will be impossible. Without concrete thresholds, monitoring endpoints, and clear scaling paths, this mitigation is completely ineffective.
