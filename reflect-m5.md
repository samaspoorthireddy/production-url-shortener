# Module 5 Reflection: Stakeholder Communication

## Knowledge Check: Comprehension Questions

### 1. What core problem does this module solve in stakeholder communication?
This module solves the problem of audience misalignment where engineers present low-level technical implementation details and jargon to business stakeholders. It teaches engineers to translate complex system designs, technical debt, and risks into business outcomes (such as launch delays, revenue risks, and security issues) that product managers, VPs, and executives can understand and act upon.

### 2. Which decision in this module has the biggest impact, and why?
The decision on the communication medium (Option A: Written Memo vs. Option B: Visual Presentation) has the biggest impact. This choice determines the shelf life, scalability, and clarity of the decision. A written memo operates asynchronously, scales to any number of teams, is forwardable, and serves as a durable archive of the architectural decision, whereas a presentation is ephemeral and limited by calendar availability.

### 3. What evidence proves the implementation works end-to-end?
The end-to-end validation is demonstrated by the rewritten stakeholder communications (`launch-delay-memo.md` and `gateway-memo-rewritten.md`). They successfully:
* Lead with business impact (e.g., delaying the subscription launch by 3 weeks, or upgrading the gateway to prevent holiday slowdowns).
* Translate or eliminate all technical jargon (e.g., replacing "token replay vulnerability" with "unauthorized card charges" and "mTLS/Kong/NGINX" with "traffic routing system").
* Use simple analogies (photocopied coat-check tickets and unlocked delivery vans) to make technical tradeoffs visceral.
* Conclude with clear, actionable asks (requesting timeline shift approvals and meeting schedules).

---

## Mini Practical Task: Verification Action (Check 1: The Opening Sentence)

### Artifact Excerpt:
> **SUBJECT: Q3 Proposal: Upgrading Our Traffic Routing System to Prevent Checkout Failures**  
> We are proposing to replace our traffic routing system in Q3 to prevent the checkout slowdowns that impacted our customers last year. The migration will take 8 weeks and requires dedicated engineering resources.

### Note on What Was Changed and Why:
* **Before:** Marcus's original draft opened with: *"I wanted to flag an important infrastructure change that the platform team is planning for Q3. Our current API gateway is running on an EOL version of Kong (2.8.x)..."*
* **After:** We rewrote the opening to state the business impact and consequence immediately: upgrading the system to prevent repeat checkout failures. 
* **Why:** The original opening used terms like "API gateway" and "EOL version of Kong" which are engineering details that product managers do not care about. The rewritten opening answers the stakeholder's immediate question: *"Why should I stop what I am doing and read this?"* by linking the work to system stability and customer checkout uptime.

---

## Risk and Mitigation
* **Risk:** In translating technical risks to non-technical language, an engineer might over-simplify (e.g., saying "we are making the database better") to the point where the stakeholder has no substance to make a decision or weigh trade-offs.
* **Mitigation:** Focus on *translation* rather than simplification. Keep all the key facts intact (such as duration, impact, and specific resources needed) but explain them using business terms (cost, customer experience, safety) and clear analogies.
