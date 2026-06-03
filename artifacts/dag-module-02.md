# Module 2: Dependency DAG (Directed Acyclic Graph)

This document maps the buildable work items for the SkillSwap platform and outlines their technical dependency relationships, incorporating a cycle-breaking node split for the provider vetting and approval system.

---

## 1. Buildable Work Items
We have grouped the requirements from Module 1 into 13 buildable work items:
1. **User Authentication** (`UserAuth`): Login, signup, password resets, and session management.
2. **Listings Data Model** (`ListingsModel`): Database schema for provider profiles (in pending/approved states), descriptions, pricing, and category taxonomy.
3. **Provider Onboarding & Vetting** (`ProviderVetting`): Submission pipeline for provider credentials, background check uploads, and profile details.
4. **Admin Review Tool (Minimal)** (`AdminReviewTool`): A lightweight interface (or CLI utility) that lets administrators view pending providers and approve/reject them.
5. **Availability Management** (`Availability`): Setting time slots and calendars, including double-booking checks.
6. **Search & Browse** (`SearchBrowse`): Search input, categories browsing, and performance tuning for "feels instant."
7. **Booking Flow** (`BookingFlow`): Reserving slots, conflict validation, and matching users to slots.
8. **Payment Processing** (`Payments`): Handling Stripe charges, pre-authorizations, and 15% platform split calculations.
9. **Cancellation Flow** (`Cancellation`): Releasing slots, calculating refunds, and execution of platform-first or provider policies.
10. **Review System** (`Reviews`): Ratings on provider profiles, flagging no-show users.
11. **Dispute Resolution** (`DisputeResolution`): Dispute workflow, user-provider communication.
12. **Admin Dashboard (Full)** (`AdminDash`): Operations dashboard including full analytics, dispute escalations, and financial tracking.
13. **Notification System** (`Notifications`): Sending transactional emails for bookings, confirmations, and cancellations.

---

## 2. Visual Dependency DAG (ASCII Diagram)

```text
           [UserAuth]               [ListingsModel]
               │                           │
               │                           H
               │                           ▼
               │                    [ProviderVetting]
               │                           │
               │                           H
               │                           ▼
               │                    [AdminReviewTool]
               │                           │
               │                           H
               │                           ▼
               │     [SearchBrowse] ◄── [Availability]
               │                               │
               │                               H
               │                               ▼
               └───────────────────────► [BookingFlow]
                                               │
             ┌─────────────────┬───────────────┴───────────────┐
             │                 │                               │
             H                 H                               H
             ▼                 ▼                               ▼
         [Payments]        [Reviews]                  [DisputeResolution]
             │                 │                               │
             H                 S                               H
             ▼                 ▼                               ▼
       [Cancellation] ─────────┼─────────► [AdminDash] ◄───────┘
             │                 │
             S                 │
             ▼                 ▼
      [Notifications] ◄────────┘
```

*Note: (H) represents a Hard dependency (solid constraint), and (S) represents a Soft dependency (negotiable/mockable relationship).*

---

## 3. Dependency Relations Table

| Dependency Connection (From --> To) | Type (H / S) | Technical Rationale |
|---|---|---|
| `ListingsModel` --> `ProviderVetting` | Hard (H) | Vetting details must map to a database schema containing provider data. |
| `ProviderVetting` --> `AdminReviewTool` | Hard (H) | Vetting submission records are required before administrators can review them. |
| `AdminReviewTool` --> `Availability` | Hard (H) | A provider must pass vetting (transition to "Approved") before they can publish availability. |
| `Availability` --> `BookingFlow` | Hard (H) | Time slots must be set by a provider before a booking can occur. |
| `UserAuth` --> `BookingFlow` | Hard (H) | Bookings must link to a valid, authenticated user account. |
| `BookingFlow` --> `Payments` | Hard (H) | Payments must process against a specific, valid booking instance. |
| `BookingFlow` --> `Reviews` | Hard (H) | Reviews can only be submitted against a completed session/booking. |
| `BookingFlow` --> `DisputeResolution` | Hard (H) | Disputes can only be raised against a valid booking transaction. |
| `Payments` --> `Cancellation` | Hard (H) | A refund payout cannot occur without a corresponding charge transaction ID. |
| `BookingFlow` --> `Notifications` | Soft (S) | Mail notification calls can be stubbed/mocked during booking construction. |
| `Cancellation` --> `Notifications` | Soft (S) | Cancellation emails can be stubbed during initial development. |
| `DisputeResolution` --> `AdminDash` | Hard (H) | Admin dashboard dispute management requires dispute submission schemas. |
| `Payments` --> `AdminDash` | Hard (H) | The financial operations dashboard requires payment transactional data. |
| `Reviews` --> `AdminDash` | Soft (S) | Dashboard analytics can be built before the review system is fully operational. |
| `Availability` --> `SearchBrowse` | Soft (S) | Search can display general provider profiles before availability filtering is integrated. |

---

## 4. Starting and End Points

### Starting Points (No Incoming Dependencies)
- `UserAuth` (Can be built and tested independently)
- `ListingsModel` (Forms the foundational schema layer for all provider actions)

### End Points (No Outgoing Dependencies)
- `SearchBrowse` (Consumer search/browse API; no downstream features block on search)
- `AdminDash` (Full operational operations view; built after core transaction features)
- `Notifications` (Downstream utility; can be built and hooked up late in the project)
