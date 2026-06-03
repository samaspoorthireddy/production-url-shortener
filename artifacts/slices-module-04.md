# SkillSwap Vertical Slicing Plan

This document outlines the delivery roadmap for the SkillSwap platform using vertical slices. Each slice cuts end-to-end through the user interface, backend logic, and database layer, ensuring that every increment is a testable feature rather than an isolated technical foundation.

---

## Slice 1: Provider Profile & Listing Creation (Ultra-Thin MVP)

*   **Name**: Provider Profile & Listing Creation (Ultra-Thin MVP)
*   **Scope (What Is In)**:
    *   **Data Layer**: Simple database table for `providers` and `services`.
    *   **Logic Layer**: Backend route to create a provider listing and write to database.
    *   **Interface Layer**: A clean HTML/JS submission form (`/provider/new`) and a listing detail view (`/provider/<id>`).
    *   **Features**: A provider can input their name, category, service name, hourly rate, and description. Submitting the form writes to the database and redirects to the profile page showing these details.
*   **Anti-Scope (What Is Explicitly Out)**:
    *   No authentication or login (all listing creation and profile visits are anonymous).
    *   No calendar/availability setup (cannot define dates or slots).
    *   No admin verification or vetting pipeline (listings are published instantly).
    *   No client browse or search interfaces (homepage does not display directory yet).
    *   No booking engine or payment flow.
*   **Dependencies**: None.
*   **Acceptance Criteria**:
    1. Navigate to `/provider/new`.
    2. Fill in: Name (`John Doe`), Category (`Tutoring`), Service Name (`Calculus 101`), Rate (`$50/hr`), and Description (`Calculus tutoring`).
    3. Click "Submit".
    4. Verify the browser redirects to `/provider/1` and displays all input information correctly.
    5. Refresh the page and verify the data persists from the database.
*   **Estimated Complexity**: S (Small - 2 hours)

---

## Slice 1.5: Stripe Payments Sandbox Spike

*   **Name**: Stripe Payments Sandbox Spike
*   **Scope (What Is In)**:
    *   **Data Layer**: None (no persistence yet).
    *   **Logic Layer**: Backend route to generate a Stripe Checkout Session with hardcoded amount ($50.00) in test mode; a webhook listener endpoint (`/payments/webhook`) to handle and log Stripe checkout completion events.
    *   **Interface Layer**: Standalone prototype route (`/payments-demo`) with a "Test Payment" button, and a success redirection route (`/payments/success`).
    *   **Features**: Clicking the button redirects to the Stripe-hosted test checkout page. Completing the form redirects to our success page and fires a webhook logged by our backend server.
*   **Anti-Scope (What Is Explicitly Out)**:
    *   No integration with the provider profiles or active bookings database.
    *   No persistence of transaction details to our database.
    *   No client booking options, scheduling slot checks, or cancellation/refund functionality.
*   **Dependencies**: None.
*   **Acceptance Criteria**:
    1. Navigate to `/payments-demo`.
    2. Click the "Test Payment" button.
    3. Verify redirect to Stripe's Hosted Checkout page showing $50.00.
    4. Fill in test card details and submit.
    5. Verify redirect to `/payments/success` showing "Payment Successful".
    6. Inspect backend server logs to verify the `checkout.session.completed` event is received and logged.
*   **Estimated Complexity**: S (Small - 2 hours)

---

## Slice 2: Provider Onboarding & Admin Vetting

*   **Name**: Provider Onboarding & Admin Vetting
*   **Scope (What Is In)**:
    *   **Data Layer**: Add a state enum `status` (`pending_approval`, `approved`, `rejected`) to the provider schema.
    *   **Logic Layer**: Logic to restrict detail view access based on status.
    *   **Interface Layer**: Admin review page (`/admin/review`) displaying a queue of pending listings, with "Approve" and "Reject" buttons.
    *   **Features**: Newly created listings enter `pending_approval` status. Viewing a pending listing shows a "Listing under review" notice instead of the profile details. Approved listings show the full profile details.
*   **Anti-Scope (What Is Explicitly Out)**:
    *   No admin authentication (the admin review page is publicly accessible for now).
    *   No automated email or push notifications (vetting outcomes are database-only).
    *   No custom reason input for rejection (binary approve/reject decision only).
*   **Dependencies**: Slice 1
*   **Acceptance Criteria**:
    1. Create a new provider listing via `/provider/new`.
    2. Verify navigating to `/provider/2` displays a "Listing under review" notice.
    3. Navigate to `/admin/review`, locate the listing, and click "Approve".
    4. Re-visit `/provider/2` and verify the profile details are now fully visible.
*   **Estimated Complexity**: S (Small - 2 hours)

---

## Slice 3: Availability Calendars & Booking Engine (Stubbed Payments)

*   **Name**: Availability Calendars & Booking Engine (Stubbed Payments)
*   **Scope (What Is In)**:
    *   **Data Layer**: Database tables for `time_slots` and `bookings`.
    *   **Logic Layer**: Validation to prevent booking conflicts (double-booking the same slot) and implementation of the `process_payment` stub interface contract (returning instant mock success).
    *   **Interface Layer**: Slot management panel for providers (`/provider/<id>/availability`), slot selector on the provider's profile page, and a checkout page (`/booking/checkout`).
    *   **Features**: Approved providers can create individual availability slots (Date + Start/End Time). Clients can view slots, pick one, enter their email on checkout, and click "Book". Submitting triggers the payment stub, reserves the slot, and generates a booking confirmation page (`/booking/confirm/<id>`).
*   **Anti-Scope (What Is Explicitly Out)**:
    *   No real-money Stripe transaction routing (uses stub/mock payments).
    *   No user/client authentication (clients book anonymously with email address input).
    *   No booking cancellation, modifications, or refund paths.
    *   No search or filtering engine (users must navigate directly to the provider URL).
*   **Dependencies**: Slice 2
*   **Acceptance Criteria**:
    1. Navigate to `/provider/1/availability` and create a slot for tomorrow at 2:00 PM.
    2. Navigate to the profile page `/provider/1`, select the 2:00 PM slot, and click "Book".
    3. Enter client email `client@example.com` and submit.
    4. Verify booking confirmation screen displays a unique booking ID and transaction receipt code `stub_txn_12345`.
    5. Navigate back to `/provider/1` and verify the 2:00 PM slot is no longer visible for selection.
*   **Estimated Complexity**: M (Medium - 4-6 hours)

---

## Slice 4: Authentication & Search/Browse Directory

*   **Name**: Authentication & Search/Browse Directory
*   **Scope (What Is In)**:
    *   **Data Layer**: Database table for `users` with hashed passwords and user-role relations (`provider` or `client`).
    *   **Logic Layer**: Login, logout, session management, and database query index optimizations.
    *   **Interface Layer**: Authentication screens (`/login`, `/signup`), client/provider dashboards, and a search-enabled homepage directory (`/`).
    *   **Features**: Providers can log in to edit only their own profile and calendar slots. Clients can log in to view their personal booking history on a dashboard. The homepage displays all approved providers and allows filtering by category and instant-search (optimized to execute in under 100ms).
*   **Anti-Scope (What Is Explicitly Out)**:
    *   No password recovery or email verification flows.
    *   No notification alerts (no SMS/email integrations yet).
    *   No advanced dashboard metrics or analytics graphs.
*   **Dependencies**: Slice 3
*   **Acceptance Criteria**:
    1. Navigate to `/provider/1/availability` without an active session and verify redirect to `/login`.
    2. Register a new user, log in, and verify access to edit their profile.
    3. Try to access `/provider/1/availability` while logged in as a different provider; verify access is denied.
    4. Log in as a client, search for "Calculus" on the homepage, select the provider instantly, and book a slot. Verify the booking appears on the client's home dashboard.
*   **Estimated Complexity**: M (Medium - 4-6 hours)

*   *Note on Performance Verification*: The search endpoint latency will be verified via backend query profiling/timing logs showing execution time `< 100ms`.

---

## Slice 5: Live Stripe Integration & Cancellation State Machine

*   **Name**: Live Stripe Integration & Cancellation State Machine
*   **Scope (What Is In)**:
    *   **Data Layer**: Refund/cancellation status tracking schema.
    *   **Logic Layer**: Business rules for cancellation windows (e.g. 24-hour rule for refunds), Stripe SDK integration, and webhook processors.
    *   **Interface Layer**: "Cancel Booking" options on dashboards and Stripe Hosted Checkout redirect components.
    *   **Features**: Replaces the payment stub with active Stripe Checkout sessions in test mode. A client can cancel an active booking from their dashboard; if the booking is > 24 hours away, a full refund is queued via the Stripe API, otherwise, a cancellation fee/no-refund logic is applied.
*   **Anti-Scope (What Is Explicitly Out)**:
    *   No multi-currency conversions (USD only).
    *   No automated tax calculations or custom invoice PDFs.
*   **Dependencies**: Slice 4
*   **Acceptance Criteria**:
    1. Log in as client, navigate to dashboard, and click "Cancel Booking" on a slot scheduled for 3 days from now. Verify status updates to `cancelled` and the slot becomes bookable on the provider's calendar.
    2. Book a slot, select Stripe test-mode credit card checkout, verify redirection to Stripe's payment interface, fill in details, and confirm.
    3. Verify that the booking updates to `confirmed` upon payment webhook callback, and the transaction is visible in the Stripe dashboard.
*   **Estimated Complexity**: L (Large - 8-10 hours)
