# Module 1: Ambiguities and Open Questions Checklist

This checklist flags ambiguities, gaps, and contradictions in the SkillSwap specification, outlining clarifying questions for the PM and proposed resolutions.

---

## 1. Ambiguities & Open Questions

### Ambiguity 1: Cancellation Policy Format & Bounds
- **Context**: Paragraph 1 states that booking cancellations apply "the provider's cancellation policy."
- **Ambiguity**: Are providers allowed to enter free-form text policies, or must they choose from structured platform templates (e.g. "Full refund before 24h, 50% refund after")?
- **Clarifying Question**: "Do we support arbitrary free-text cancellation policies, or do we require providers to select from a set of structured, system-enforced templates to allow automated refund calculations?"

### Ambiguity 2: "Feel Instant" Search Latency & Load
- **Context**: Paragraph 1 mentions a search feature that "should feel instant."
- **Ambiguity**: "Instant" is subjective. Does this mean sub-100ms response times? Is search scoped to local cities or global categories? What concurrent load must sustain this?
- **Clarifying Question**: "Can we quantify 'feel instant' search performance (e.g., P95 response time < 150ms under a load of 1,000 concurrent users)? Should we implement Elasticsearch/Algolia, or is a Postgres FTS/Trigram search acceptable for the initial city launch?"

### Ambiguity 3: Vetting Criteria & Status Transitions
- **Context**: Paragraph 2 & 3 mention a provider "vetting process" and admin "approval" before going live.
- **Ambiguity**: What information is required for vetting (e.g., background checks, certificate uploads, phone verify)? Can a provider modify their profile after approval, and does it trigger re-vetting?
- **Clarifying Question**: "What are the minimal required fields for the vetting process? If an approved provider modifies their pricing or service description, does their account automatically revert to a 'pending approval' state, or do changes go live immediately?"

---

## 2. Specification Contradiction & Proposed Resolution

### The Contradiction: Automatic Policy Enforcement vs. Dispute Resolution Flow
- **Contradiction**:
  - **Paragraph 1** states cancellations are resolved immediately with the "provider's cancellation policy applied" (suggesting automated, instant refund/charge execution).
  - **Paragraph 3** introduces a "dispute resolution flow when users and providers disagree," with the admin team handling "escalated disputes."
- **The Issue**: If a user cancels and the system automatically applies a provider's cancellation policy (charging a fee/refusing a refund), does the user have the right to dispute that fee? Does the dispute flow permit overriding the automated policy? If so, when and under what criteria?
- **Proposed Resolution**:
  - **Tier 1 (Automated Execution)**: Cancellations immediately trigger the default automated refund/charge calculation according to the structured policy selected by the provider.
  - **Tier 2 (Dispute Window)**: If a cancellation occurs due to an extenuating circumstance or provider fault (e.g., provider was a no-show), the user can raise a dispute request within 48 hours of the scheduled session.
  - **Tier 3 (Admin Escalation)**: The funds are held in escrow during the dispute. If the provider and user cannot agree, the dispute is escalated to platform admins for final, manual arbitration.
