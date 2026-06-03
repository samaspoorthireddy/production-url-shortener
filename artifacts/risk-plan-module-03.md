# SkillSwap Risk-Ordered Build Plan (Revised)

This document categorizes, scores, and orders the work items for the SkillSwap platform based on their technical risk profile. It has been revised to address a business blocker: the client does not yet have a Stripe account or a merchant business entity.

---

## 1. Technical Risk Framework

To ensure clear communication within the engineering team, we categorize technical risk—defined as an unknown that could invalidate our execution plan—into four concrete categories:

1. **Integration Risk** (Analogy: planning a road trip where your route depends on a ferry crossing; if the ferry isn't running, your plan breaks): The risk of connecting our system to external services we do not control, such as third-party Application Programming Interfaces (APIs, which are programmatic ways for different software systems to talk to each other).
2. **Novelty Risk** (Analogy: you have cooked pasta a hundred times, but you have never made sourdough bread; you will encounter unpredictable issues because the process is entirely new to you): The risk of building features using technologies or concepts our team has never implemented before.
3. **Dependency Risk** (Analogy: the foundation of a house; if the foundation cracks, the entire house built on top of it is compromised): The risk associated with components at the base of our build chain that other features rely on to function.
4. **Scale Risk** (Analogy: a lemonade stand works great at the end of a driveway, but if 500 customers show up at once, the setup collapses): The risk that a system design which works fine in development will fail under high load or volume (e.g. supporting thousands of concurrent users across multiple cities).

---

## 2. Business Blocker & PM Escalation

### The Blocker
The client does not have a Stripe account or a registered business entity set up to receive payments. This is an operational/business risk rather than a technical one. We cannot integrate real Stripe money movement without active credentials.

### PM Escalation Message
> "Payment processing is blocked because the client has no Stripe account or merchant entity set up. We have defined and stubbed the payment interface contract so booking and cancellation development can continue, but end-to-end payment testing is blocked until merchant accounts are resolved. Can you obtain a timeline from the client?"

---

## 3. Isolating Blocked Work & Stubbed Interface

To keep the development team productive, we have isolated the payment dependency:
* **Blocked**: Direct money processing, real credit card transactions, actual refund processing via Stripe APIs, and charge event synchronization.
* **Not Blocked**: The payment schema, checkout forms, pricing displays, and the internal interface contract that other modules use to call payment events.

We define the following **Payment Interface Contract** (a strict programmatic boundary or input/output agreement) to mock/stub payments:

```python
def process_payment(booking_id: int, amount: float, payment_method_id: str) -> dict:
    """
    Interface contract for processing bookings.
    In development, this uses a stub (throwaway mock logic) that returns success:
    Returns:
        {
            "status": "success",
            "transaction_id": "stub_txn_12345",
            "processed_at": "2026-06-03T12:00:00Z"
        }
    """
    pass
```

Once the client resolves their merchant account blocker, we will swap the stubbed implementation inside `process_payment` with actual Stripe SDK calls. Downstream services like the booking state flow and cancellations will remain completely unchanged because they depend on the *interface contract*, not Stripe's direct library.

---

## 4. Revised Risk-Ordered Build Plan

This updated numbered sequence prioritizes retiring non-blocked high-risk items (such as calendar concurrency) while payments are stubbed:

1. **Listings Data Model (`ListingsModel`)**
   - *Risk*: 3 (Dependency, Scale)
   - *Justification*: Foundational database schema that defines provider data. Unblocks all listings and profile operations.
2. **Provider Onboarding & Vetting (`ProviderVetting`)**
   - *Risk*: 3 (Novelty)
   - *Justification*: Builds the multi-step verification state machine.
3. **Admin Review Tool (Minimal) (`AdminReviewTool`)**
   - *Risk*: 2 (Dependency)
   - *Justification*: Minimum tool to approve/reject provider profiles to unblock availability setup.
4. **Availability Management (`Availability`)**
   - *Risk*: 4 (Novelty)
   - *Justification*: High-risk calendar slot concurrency. Promoted to focus development attention here since payments are blocked.
5. **User Authentication (`UserAuth`)**
   - *Risk*: 2 (Dependency)
   - *Justification*: Foundational auth needed for user identity contexts.
6. **Booking Flow (`BookingFlow`)**
   - *Risk*: 3 (Novelty, Dependency)
   - *Justification*: Orchestrates reservation state transitions. Connects users with available slots.
7. **Payment Interface Contract + Stub (`PaymentsInterface`)**
   - *Risk*: 2 (Dependency)
   - *Justification*: Establishes the payment input/output contracts. Keeps booking and refund pipelines moving using mock success stubs.
8. **Cancellation Flow (`Cancellation`)**
   - *Risk*: 3 (Novelty)
   - *Justification*: Handles refunds and releases slots, reading status from the stubbed payment contract.
9. **Search & Browse (`SearchBrowse`)**
   - *Risk*: 3 (Scale)
   - *Justification*: High-risk latency tuning. Optimizes provider search routes for "feels instant" speeds.
10. **Dispute Resolution (`DisputeResolution`)**
    - *Risk*: 2 (Novelty)
    - *Justification*: Basic dispute flagging/escalation communication portal.
11. **Admin Dashboard (Full) (`AdminDash`)**
    - *Risk*: 2 (Integration)
    - *Justification*: Consolidated ops dashboard. Displays analytics from reviews, disputes, and transactions.
12. **Notification System (`Notifications`)**
    - *Risk*: 2 (Integration)
    - *Justification*: Delayed integration using email API stubs until integration testing.
13. **Review System (`Reviews`)**
    - *Risk*: 1 (None significant)
    - *Justification*: Standard rating CRUD built last.
14. **Payment Integration (Blocked - Waiting on Stripe credentials) (`PaymentsStripe`)**
    - *Risk*: 5 (Integration, Novelty)
    - *Justification*: Actual money movement integration. Deferred to the end of the queue because of the client's business credentials blocker.
