# Critique of Infrastructure Migration Memo (Marcus's Email)

## Part 1: Jargon Count

This email contains **48 distinct instances of technical jargon** that would be unintelligible or highly confusing to a Head of Product or non-technical stakeholder.

### Key Jargon Examples and Their Issues:
1. **"EOL version of Kong (2.8.x)"**: Refers to software nearing "End of Life" (no longer supported or updated), but doesn't explain that this exposes us to security risks. Kong is a specific vendor product name.
2. **"NGINX reverse proxy with custom Lua plugins"**: Details the underlying plumbing. Product stakeholders do not need to know NGINX or Lua; they only need to know that we are using custom-built validation software.
3. **"mTLS termination ... zero-trust policies east-west"**: High-level network security concepts. To a stakeholder, this simply means "we cannot secure traffic between our internal services."
4. **"c5.2xlarge instances"**: Specific AWS hardware sizing. This is irrelevant to business stakeholders; it should be translated into cloud hosting costs.
5. **"12,000 RPS at p95 < 200ms"**: RPS (Requests Per Second) and p95 (95th percentile response time) are raw metrics. Stakeholders care about "handling 12,000 user clicks per second with a load time under a fifth of a second."
6. **"Envoy-based ingress ... Istio sidecars ... circuit breaking ... retry budgets"**: Service mesh implementation details. These should be described as "automatic traffic rerouting and failure prevention."
7. **"WASM WASM filters ... StatsD + Grafana ... OpenTelemetry collectors ... Datadog tenant"**: Low-level database/observability vendor tools.
8. **"Blue-green deployment"**: Running the old and new systems side-by-side to prevent downtime.

---

## Part 2: Buried Business Risk

**Buried Risk text:** 
> *"Additionally, the Istio sidecar injection increases pod memory overhead by approximately 128MB per pod. With our current 340 pods, that is an additional 42.5 GB of cluster memory. We believe our current node pool has headroom, but we have not validated this against the reserved capacity for autoscaling events."*

**Plain-Language Translation (The Buried Risk):**
"If customer traffic spikes (such as during Black Friday) and our services try to automatically spin up extra copies to handle the load, we may exceed our server memory limit and crash the entire checkout system, preventing customers from placing orders during our highest-volume sales window."

---

## Part 3: Missing Actionable Asks

Marcus concludes with "Let me know if you have questions," which fails to request the required leadership decisions. He should have ended with these specific asks:

1. **Product Roadmap Tradeoff Approval:** "We need approval to dedicate 2 platform engineers for 8 weeks to this migration, which will require pausing development on the Q3 custom reports feature."
2. **Infrastructure Budget Increase Approval:** "The new setup requires an additional 42.5 GB of server memory, which will increase our monthly cloud infrastructure costs by approximately $600. We need budget approval for this increase."
3. **Migration Window Approval:** "We need approval to schedule the parallel run window in September and coordinate with the release manager to freeze new deployments during the final 2-day cutover."
