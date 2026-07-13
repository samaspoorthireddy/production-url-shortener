# REWRITTEN MEMORANDUM

**TO:** Sarah (VP of Engineering), David (Head of Product)  
**FROM:** Platform Engineering Team  
**DATE:** June 10, 2026  
**SUBJECT:** Q3 Proposal: Upgrading Our Traffic Routing System to Prevent Checkout Failures  

We are proposing to replace our traffic routing system in Q3 to prevent the checkout slowdowns that impacted our customers last year. The migration will take 8 weeks and requires dedicated engineering resources. 

---

### What Happened Last Year
During Black Friday last November, customer traffic pushed our routing system to its limit, causing a slowdown that degraded our checkout system for 47 minutes. With transaction volume projected to grow this year, our current system will not sustain another holiday spike without failing.

### Proposed Upgrade
We plan to replace our legacy routing setup with a modern, more scalable traffic system. This will consolidate our connections and build failure protection directly into our network infrastructure.

* **Timeline & Uptime:** The migration will take 8 weeks. We will run the new system in parallel with the old one, ensuring zero customer-facing downtime during the rollout.
* **Roadmap Impact:** This project requires 2 platform engineers. While they are focused on this security and scaling upgrade, they will not be available to build new Q3 product features.

### Surfaced Risk
The primary risk is that the new system requires more server memory than we currently allocate. If we do not validate our memory limits under simulated peak load before Black Friday, the checkout system could run out of memory and completely crash during our highest-sales window. We plan to run simulated load tests at 2x normal traffic in our testing environment by August 15 to prevent this.

---

### Decisions & Approvals Required
To proceed, we need the following decisions from you by Friday, June 19:

1. **Roadmap & Resource Approval:** Approval to allocate 2 platform engineers for 8 weeks starting July 1, and confirmation that pausing Q3 feature commitments to accommodate this works with the product roadmap.
2. **Testing Window Decision:** A decision on whether to run the simulated load tests in our testing environment during business hours (enables faster engineering feedback but carries a minor risk of temporary internal test-system lag) or off-hours (requires scheduling evening/weekend coverage).
