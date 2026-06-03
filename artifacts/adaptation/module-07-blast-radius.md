# Module 07 Blast Radius Analysis

This document evaluates the impact of the newly introduced B2B "Company Accounts" requirements and the 6-day compressed timeline constraint across our existing planning artifacts.

---

## 1. Company Accounts Impact Matrix (Minimal Bridge Strategy)

We are implementing Option B (Minimal Bridge) to fit within the 6-day investor demo timeline. 

| Artifact | Impact | Technical Detail & Affected Surface |
|----------|--------|------------------------------------|
| **User data model** | **MAJOR** | Add `company_name` (nullable String) and `can_book_for_others` (Boolean, default False) fields to the User table. Requires a lightweight DB migration script. |
| **Auth/JWT system** | **MINOR** | Ensure user registration/login endpoints return `company_name` and `can_book_for_others` claims inside the JWT token to avoid repeated DB hits on the frontend. |
| **Booking flow (API)** | **MAJOR** | Modify `ss-104` schema. Add `booked_for_name` (nullable String) and `booked_for_email` (nullable String) to request payload validation schemas. If booking user has `can_book_for_others == True`, these delegation fields are validated and stored in the database. |
| **Booking flow (UI)** | **MAJOR** | Update the booking confirmation modal. Render a conditional "Book for employee" checkbox when `can_book_for_others` is true, displaying text inputs for the employee's Name and Email. |
| **Provider dashboard** | **MINOR** | Update provider booking list queries to display `booked_for_name` and `booked_for_email` if populated, showing who is attending the session instead of just the administrator account. |
| **Search/listing** | **NO IMPACT** | Searching and listing providers is unaffected by the booking delegation or company accounts logic. |
| **Payment/billing** | **MINOR** | Keep payments on the booking user's credit card/account. Receipt meta-data is enriched with `company_name` and `booked_for_name` for auditability and manual employee reimbursement. |
| **Interface contracts** | **MINOR** | Update the shared booking endpoint spec (`PUT /api/bookings`) to accept optional delegation metadata (`booked_for_name`, `booked_for_email`). |
| **Tickets: completed** | **MINOR** | `SS-101` (DB setup) requires an update to add the new database columns to `users` and `bookings` schemas via a patch migration. |
| **Tickets: in progress** | **NO IMPACT** | `SS-102` (Provider profile onboarding) is independent of user account structure and delegation. |
| **Tickets: not started** | **MAJOR** | `SS-104` (Booking transaction engine) requires major redesign to incorporate delegation validations and DB schemas before coding begins. |

---

## 2. Compressed Timeline Categorization (6-Day Scope)

We have prioritized outstanding tasks to ensure the core value loop (Sarah booking a service with Mike) functions while supporting B2B company accounts.

* **MUST SHIP (Required for Demo + Deal)**
  * **SS-103 (Provider Slot Lookup / Availability lookup)**: Required so corporate bookers can query active calendar availability before booking.
  * **SS-104 (Provider Booking Transaction Engine)**: The core engine where transaction takes place. Must support `booked_for_name` and `booked_for_email` validations.
  * **SS-107 (Delegation DB Migration & User Schema Patch)**: New ticket to support the company account model addition.
  
* **SHOULD SHIP (High Priority but Descoped if Blocked)**
  * **Interactive Booking confirmation emails**: Replace with simple system logging (`logger.info("Booking notification sent to employee...")`) to save integration time.
  
* **CUT (Deferred post-demo)**
  * **Advanced Category Filters**: Cut. Search is restricted to exact match lookup to simplify UI/API routing.
  * **Stripe Live Payment Gateway**: Cut. We will use simulated checkout confirmations instead of live Stripe integration to avoid environment keys setup delay.
  * **Provider Analytics Dashboard**: Cut. Dashboard will show list of bookings only; graphical charts and revenue metrics are deferred.

---

## REVISION 2: Role-Based Access Control & Department Visibility

A new requirement addition specifies distinct roles (Managers, Employees, Department Heads) and department-level booking visibility bounds.

### 1. Strategic Decision Pivot: Shifting to Constrained Option A (Proper Model)
The original "Minimal Bridge" (Option B - boolean flag) is no longer viable. Implementing roles and department structures via ad-hoc columns on a flat user table creates insecure validation paths.
* **Pivot**: We will build a structured relational model—introducing an `Organization` model, a `Department` model, and a `UserRole` enum (`manager`, `employee`, `dept_head`)—but **strictly constrain seed data**. No user-facing interfaces will be built for creating departments or editing roles; these will be seeded via backend scripts, keeping the 6-day timeline viable.

### 2. Escalation & New Blast Radius Matrix

| Surface | Original Impact | Revised Impact | Technical Detail & Affected Surface |
|---------|-----------------|----------------|-------------------------------------|
| **User data model** | MAJOR | **CRITICAL** | Introduce `departments` table (id, name, organization_id) and `UserRole` enum. Users table adds `role` (enum) and `department_id` (foreign key). |
| **Auth/JWT system** | MINOR | **MAJOR** | Auth JWT token payload must encode `role` and `department_id` to enable middleware authorization checks on resource lookup. |
| **Booking lookup (API)** | NO IMPACT | **MAJOR** | `GET /api/bookings` requires role-based scoping: Employees see only their bookings (`user_id == current_user_id`); Department Heads see all bookings matching their `department_id`; Managers see all organization bookings. |
| **Search/listing** | NO IMPACT | NO IMPACT | No change. Browsing providers remains public and role-agnostic. |
| **Interface contracts** | MINOR | **MAJOR** | Booking GET endpoints must define structural queries (scoping by employee, department, or organization) and return `403 Forbidden` if permissions are violated. |
