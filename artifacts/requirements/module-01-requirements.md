# Module 1: Full Requirements Document

This document presents a structured requirements list for SkillSwap, categorized by type (Functional, Constraint, Quality Attribute) and stakeholder (User/Learner, Provider, Platform/Ops).

---

## Stakeholder: User (Learner)

### Functional Requirements
1. **Browse Providers by Category**
   - *Requirement*: Users must be able to browse service providers categorized by service types.
   - *Source*: Paragraph 1 (Explicit).
   - *Confidence*: High.
2. **View Profiles with Ratings**
   - *Requirement*: Users must be able to view detailed provider profiles, including rating scores and written reviews.
   - *Source*: Paragraph 1 (Explicit).
   - *Confidence*: High.
3. **Book Time Slots**
   - *Requirement*: Users must be able to select and reserve specific available time slots.
   - *Source*: Paragraph 1 (Explicit).
   - *Confidence*: High.
4. **Pay Through Platform**
   - *Requirement*: Users must be able to pay for sessions directly through platform-supported payment methods.
   - *Source*: Paragraph 1 (Explicit).
   - *Confidence*: High.
5. **Get Confirmation Emails**
   - *Requirement*: Users must receive automated confirmation emails containing booking and payment details upon successful checkout.
   - *Source*: Paragraph 1 (Explicit).
   - *Confidence*: High.
6. **Cancel Bookings** [BLOCKED - Pending PM Decision]
   - *Requirement*: Users must be able to cancel bookings, with refund rules and fee calculations determined once the cancellation policy conflict is resolved.
   - *Source*: Paragraph 1 (Explicit).
   - *Confidence*: High (Blocked).
7. **User Authentication (Signup/Login)**
   - *Requirement*: Users must be able to create an account, log in securely, and manage their learner profiles.
   - *Source*: Silence Pass (Implicit).
   - *Confidence*: High.

### Quality Attributes
8. **Instant Search Response**
   - *Requirement*: The search feature must execute queries and display results with sub-second responsiveness (targeting <150ms latency) to feel "instant".
   - *Source*: Paragraph 1 (Explicit).
   - *Confidence*: High.

---

## Stakeholder: Provider

### Functional Requirements
9. **Manage Service Profile**
   - *Requirement*: Providers must be able to set and edit service descriptions, price rates, and calendars/availability.
   - *Source*: Paragraph 2 (Explicit).
   - *Confidence*: High.
10. **Provider Dashboard**
    - *Requirement*: Providers must have a secure dashboard display showing upcoming bookings, total earnings, and historical ratings/reviews.
    - *Source*: Paragraph 2 (Explicit).
    - *Confidence*: High.
11. **Flag No-Show Users**
    - *Requirement*: Providers must be able to flag learners who fail to attend sessions.
    - *Source*: Paragraph 2 (Explicit).
    - *Confidence*: High.
12. **Submit for Vetting**
    - *Requirement*: New providers must submit profile details for platform vetting before going live.
    - *Source*: Paragraph 2 (Explicit).
    - *Confidence*: High.

---

## Stakeholder: Platform / Ops

### Functional Requirements
13. **Approve Providers**
    - *Requirement*: Platform admins must be able to review, approve, or reject new provider vetting submissions.
    - *Source*: Paragraph 3 (Explicit).
    - *Confidence*: High.
14. **Dispute Resolution Flow**
    - *Requirement*: The system must support an automated/semi-automated workspace for users and providers to raise and resolve booking disagreements.
    - *Source*: Paragraph 3 (Explicit).
    - *Confidence*: High.
15. **Escalated Dispute Handling**
    - *Requirement*: Platform administrators must have workflows to intervene and manually resolve escalated user-provider disputes.
    - *Source*: Paragraph 3 (Explicit).
    - *Confidence*: High.
16. **Payout Processing**
    - *Requirement*: The system must calculate and schedule payouts to providers (85% share) after subtracting the platform commission.
    - *Source*: Silence Pass (Implicit).
    - *Confidence*: High.

### Constraints
17. **15% Platform Commission**
    - *Requirement*: The billing system must deduct a fixed 15% commission from each transaction before paying out providers.
    - *Source*: Paragraph 2 (Explicit).
    - *Confidence*: High.
18. **Timeline & Geographic Scope**
    - *Requirement*: The architecture must accommodate expanding from one initial city to 5 cities within 6 months of launch.
    - *Source*: Paragraph 3 (Explicit).
    - *Confidence*: High.
19. **Team Capacity**
    - *Requirement*: Solution architecture must be buildable by the existing small team (2 backend developers, 1 frontend developer).
    - *Source*: Paragraph 3 (Explicit).
    - *Confidence*: High.
20. **Double-Booking Prevention**
    - *Requirement*: Database constraints or transaction controls must guarantee a time slot cannot be double-booked by concurrent reservation requests.
    - *Source*: Silence Pass (Implicit).
    - *Confidence*: High.

### Quality Attributes
21. **Initial City Scalability**
    - *Requirement*: The system must support concurrent load and transaction throughput for "at least a few thousand users" in the first city.
    - *Source*: Paragraph 3 (Explicit).
    - *Confidence*: High.
22. **Comprehensive Analytics**
    - *Requirement*: The platform must track, record, and expose telemetry/analytics for key lifecycle events (searches, bookings, cancellations, payouts).
    - *Source*: Paragraph 3 (Explicit).
    - *Confidence*: High.

---

## 🔒 Spec Contradiction: Cancellation Policies

### Description of Conflict
The specification contains a direct contradiction regarding booking cancellations:
1. **Original Spec (Paragraph 1 & 2)**: Cancellations are handled according to the provider's specific, self-defined cancellation policy.
2. **Clarification (Updated Paragraph 1)**: All cancellations made within 24 hours of booking receive a full refund, regardless of reason. Cancellations after 24 hours are non-refundable, platform-wide.

### Affected Requirements
This decision directly blocks or alters the implementation of the following downstream requirements:
- **Requirement 4 (Pay Through Platform) & Requirement 16 (Payout Processing)**: Refund flow automation, Stripe reverse transfers, and commission adjustment rules are dependent on the cancellation/refund window.
- **Requirement 9 (Manage Service Profile)**: Whether providers are allowed to configure cancellation settings in their profiles.
- **Requirement 10 (Provider Dashboard)**: How earnings are projected and shown (escrow holds vs immediate payout updates during the potential cancellation window).

### Proposed Options for PM Decision

#### Option 1: Platform-First Cancellation Policy
- **Rule**: The platform sets a universal cancellation policy: full refund within 24 hours of booking, non-refundable after. Providers cannot override this.
- **Stakeholders Affected**: Users get a simple, consistent experience. Providers lose the ability to set custom policies suited to their specific fields.
- **Trade-off**: High user consistency, lower provider flexibility. Simpler to implement.

#### Option 2: Provider Policy with Platform Floor (Hybrid)
- **Rule**: Providers set their own cancellation policies, but the platform enforces a universal minimum protection floor (e.g. users always get a full refund if they cancel within 1 hour of booking as a "cooling-off" period). Beyond that hour, the provider's custom policy applies.
- **Stakeholders Affected**: Users get a platform safety net. Providers retain autonomy for longer-term cancellations.
- **Trade-off**: Higher complexity to build (must support custom rule models, display them in the UI, and parse them in the booking engine), but satisfies both user and provider needs.

