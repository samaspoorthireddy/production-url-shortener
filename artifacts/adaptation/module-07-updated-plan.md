# Module 07 Updated Execution Plan

This document details the updated ticket plan and scope adjustments for the 6-day investor demo timeline, incorporating B2B company account support under a Minimal Bridge strategy.

---

## 1. Preserved Tickets

These tickets are already completed or in progress and remain completely unchanged:
* **`SS-102` (Provider Onboarding)**: Implemented in Module 6. Registration and profile setup endpoints work as contracted.
* **`SS-105` (Admin Vetting & Approval)**: Implemented in Module 6. PUT endpoint for status updates works as contracted.

---

## 2. Modified Tickets

These existing tickets are modified to support B2B company accounts:
* **`SS-101` (Core DB Models)**: 
  * *Status*: Done, but requires an incremental patch.
  * *Changes*: Add a new migration script to add `company_name` (string, nullable) and `can_book_for_others` (boolean, default False) to `users` model, and `booked_for_name` (string, nullable) and `booked_for_email` (string, nullable) to `bookings` model.
* **`SS-104` (Provider Booking Engine)**: 
  * *Status*: Not started.
  * *Changes*: Modify the booking request validation schema to accept optional `booked_for_name` and `booked_for_email`. Add backend validation: if user has `can_book_for_others == True`, delegation info is persisted; otherwise, if delegation fields are submitted by a non-admin user, return a `400 Bad Request` or ignore them.

---

## 3. Cut Tickets

These tickets are removed from the 6-day demo scope:
* **Live Stripe Payment Integration**: 
  * *Reason for Cut*: Standard Stripe setup, webhooks, and key configurations take at least 1-2 days of environment setup.
  * *Safety Rationale*: We will use a mock payment transaction recorder that immediately returns success. This still validates the booking state transition and invoice creation without blocking on live API endpoints.
* **Advanced Search Filters**: 
  * *Reason for Cut*: Implementing multi-attribute filters (distance, rating, category filters) adds UI and database query complexity.
  * *Safety Rationale*: We will limit search to a simple exact-match category/name string filter, which is fully sufficient to demonstrate "Browse providers" functionality.
* **Provider Analytics Dashboard**: 
  * *Reason for Cut*: Visual charts, graphs, and aggregate revenue calculations are non-critical for the core booking loop.
  * *Safety Rationale*: Providers can still view their active bookings list; the UI charts are purely aesthetic and safe to defer post-demo.

---

## 4. Added Tickets

These are new tickets created for the B2B company accounts integration:
* **`SS-107` (Delegation Migration & JWT Claims)**:
  * *Scope*: Implement DB schema patch for users/bookings tables and update user authentication tokens to include `company_name` and `can_book_for_others` claims.
  * *Estimate*: S (Small - 0.5 days)
* **`SS-108` (Booking Delegation UI Component)**:
  * *Scope*: Update the booking confirmation modal in the frontend to conditionally render employee name and email inputs if `can_book_for_others` is true.
  * *Estimate*: M (Medium - 1.0 day)

---

## REVISION 2: Role-Based Access Controls (RBAC) & Departments

With the layering of Manager, Employee, and Department Head roles and department-wide visibility bounds:

### 1. Modified Tickets (Second Pass)
* **`SS-101` (Core DB Models)**: Escalated scope. The DB patch must now create `organizations` and `departments` tables, add a `role` enum and a `department_id` foreign key constraint to `users`.
* **`SS-104` (Booking Engine & Lookup API)**: Escalated scope. The booking search endpoint `GET /api/bookings` must implement query filters checking the current user's authenticated JWT role:
  * **Employee**: filter where `user_id == current_user_id`.
  * **Department Head**: filter where `department_id == current_user_department_id`.
  * **Manager**: return all bookings for organization.
  * Return `403 Forbidden` if a user attempts to fetch details for a booking outside their permitted role boundary.

### 2. Added Tickets (Second Pass)
* **`SS-109` (RBAC JWT Integration & Middleware)**:
  * *Scope*: Implement roles and department fields in JWT token creation and write a FastAPI security dependency/middleware to check and validate access bounds for booking lookup paths.
  * *Estimate*: M (Medium - 1.0 day)

### 3. Additional Cuts (To preserve 6-day target)
* **Provider Listing Categories**: Cut. The frontend homepage will display a single static grid of all vetted providers; category browsing filters are entirely cut to save UI routing time.
* **Booking State Auditing logs**: Cut. Advanced logging of every state change in database tables is deferred.
