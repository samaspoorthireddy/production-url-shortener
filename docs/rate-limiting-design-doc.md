# Rate Limiting Proposal: Public API protection

## Problem Statement
Our public API currently lacks automated controls to manage incoming traffic volume. Last month, a single customer accidentally sent 50,000 requests per minute to our servers. This spike degraded response times for all other customers and forced our on-call engineer to wake up at 2 AM to manually block the customer's API key by editing configuration files and redeploying the service. Without automated protections, we face recurring service outages, high operational overhead, and an inability to offer paid tiers with guaranteed capacity.

## Proposed Approach
We propose implementing rate limiting (similar to a club bouncer who controls how many people can enter per minute to keep the venue from getting overcrowded). We will place this rate limiter at our API gateway (which acts like the front door of a venue, routing incoming traffic to the correct backend service). Checking requests at this entry point protects our backend services from ever seeing the traffic spike.

To track how many requests each client has remaining, we will store the client request counts in Redis (a shared in-memory database that serves as a shared whiteboard where servers can read and write data almost instantly). Using a central store allows us to enforce limits globally across all our application servers.

For the rate limiting logic, we will use the Token Bucket algorithm (where each user has a virtual bucket of tokens representing allowed requests, refilling at a steady rate, like a prepaid transit card that gets topped up with a new ride token at a steady rate). When a client sends a request, the system checks if a token is available in their bucket. If a token exists, the request is allowed and a token is consumed. If the bucket is empty, the request is rejected immediately. This algorithm easily handles temporary bursts of traffic while ensuring long-term usage stays within safe limits.

## Alternatives Considered

### Alternative 1: Sliding Window algorithm in application code with in-memory caching
We considered using the Sliding Window algorithm (which dynamically tracks requests over the last 60 seconds, like checking the speed of a car using a moving average). Under this alternative, each application server would count requests in local memory without a central database.

This approach requires no new infrastructure, which lowers operational complexity. However, because application servers do not share memory, a load balancer (which acts like a host at a busy restaurant who distributes arriving guests to the least busy tables) would distribute requests across multiple servers. A client could bypass their rate limit by sending requests to different servers, making it impossible to enforce a strict global limit.

### Alternative 2: Fixed Window algorithm at the API gateway using Redis
We also considered using the Fixed Window algorithm (which resets request counters for each customer at the start of every minute, like resetting a stop-watch at the start of every hour). We would store these counters in Redis at the API gateway level.

This approach is simple to implement because it only requires incrementing a counter in Redis that expires every minute. The downside is that clients can send twice their limit near the window boundaries. For example, if the limit is 100 requests per minute, a client can send 100 requests in the last second of minute one, and another 100 requests in the first second of minute two. This spike of 200 requests in two seconds could still overload our backend services.

## Risks and Mitigations

### Redis as a single point of failure
Because we check Redis on every API request, a Redis crash would stop all incoming traffic. To mitigate this single point of failure (a vulnerability where a single component's breakdown stops the entire system), we will implement a fail-open strategy. If the API gateway cannot reach Redis, it will log a critical alert and temporarily allow all traffic to pass through. This prioritizes service availability over strict rate enforcement during an infrastructure incident.

### Performance latency
Querying Redis on every incoming request introduces latency (the delay or wait time experienced by clients when making requests). To minimize this delay, we will run Redis on dedicated hardware in the same cloud region and data center as our API gateway. Based on our network benchmark tests, this keeps the latency overhead under 2 milliseconds per request, which is imperceptible to our users.

### The risk of doing nothing
If we do not implement a rate limiter, our API will remain vulnerable to accidental and malicious traffic spikes. Our engineering team will continue to suffer from on-call fatigue due to manual middle-of-the-night interventions. Additionally, we will be unable to launch paid subscription tiers because we cannot guarantee capacity or restrict free users.

## Open Questions
- What capacity limits should the product team establish for the free tier versus the paid tiers?
- Should we return standard headers showing clients their remaining limits and the delay before they can retry?
