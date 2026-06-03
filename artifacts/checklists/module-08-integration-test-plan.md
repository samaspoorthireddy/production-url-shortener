# Module 08 Automated Integration Test Plan

This document establishes the cross-component integration tests that must run automatically in the CI/CD pipeline on every merge to verify system-level correctness.

---

## 1. Test 1: Admin Provider Vetting & Search Visibility
* **Components Involved**: `Onboarding API` (Stream A), `Vetting API` (Stream B), `Search/Listing API`.
* **Setup**: No pre-existing providers. Clear database state.
* **Steps**:
  1. Register provider "Jane's Plumbing" (`POST /api/providers`).
  2. Execute query `GET /api/providers/search?q=Plumbing`. Verify search returns an empty list `[]` (provider is in `pending_approval` state).
  3. Admin approves Jane's Plumbing (`PUT /api/providers/{jane_id}/status` with `X-Admin-Key` header and payload `{"status": "approved"}`).
  4. Re-execute query `GET /api/providers/search?q=Plumbing`.
* **Expected Result**: Search now returns Jane's Plumbing profile with a `200 OK` status.
* **Contract Points Validated**: `POST /api/providers` schema, `PUT /api/providers/{id}/status` transition, `GET /api/providers/search` status scoping.

---

## 2. Test 2: B2B Booking Delegation Validation (Positive & Negative Paths)
* **Components Involved**: `Auth Middleware`, `Booking Creation API`.
* **Setup**: Seed user account John (role = `employee`) and user account Sarah (role = `manager`, company = `Meridian`). Seed approved provider Mike with open slot `slot-123`.
* **Steps**:
  1. Authenticate John. john-token calls `POST /api/bookings` with payload `{ "provider_id": "{mike_id}", "slot_id": "{slot_id}", "booked_for_name": "Alice", "booked_for_email": "alice@meridian.com" }`.
  2. Authenticate Sarah. sarah-token calls `POST /api/bookings` with the identical payload.
* **Expected Result**:
  * John's call returns `403 Forbidden` with body `{"detail": "Employees cannot delegate bookings to others"}`.
  * Sarah's call returns `201 Created` returning a confirmed booking record containing John's delegation info in the DB.
* **Contract Points Validated**: `POST /api/bookings` delegation schemas, Auth token role validation scopes.

---

## 3. Test 3: Department Head Visibility Scoping (Negative Path Isolation)
* **Components Involved**: `Auth Middleware`, `Booking Search API`.
* **Setup**: 
  * Seed Robert (role = `dept_head`, `department_id = 4` (Sales)).
  * Seed Kevin (role = `dept_head`, `department_id = 5` (Engineering)).
  * Seed a confirmed booking `booking-99` under `department_id = 4` (Sales).
* **Steps**:
  1. Authenticate Robert. robert-token calls `GET /api/bookings`.
  2. Authenticate Kevin. kevin-token calls `GET /api/bookings`.
  3. Authenticate Kevin. kevin-token calls `GET /api/bookings/booking-99`.
* **Expected Result**:
  * Robert's query returns a list containing `booking-99`.
  * Kevin's query returns an empty list `[]` (since no Engineering bookings exist).
  * Kevin's direct detail request for `booking-99` returns `403 Forbidden` with body `{"detail": "Access to booking details denied for this department role"}`.
* **Contract Points Validated**: `GET /api/bookings` filter scope contracts, single-resource retrieval permission boundaries.
