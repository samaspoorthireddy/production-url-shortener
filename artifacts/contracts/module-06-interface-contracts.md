# Module 06 Interface Contract: Provider Onboarding & Admin Vetting

This contract establishes the shared interfaces, schemas, and database dependencies between **Stream A (SS-102: Provider Onboarding)** and **Stream B (SS-105: Admin Vetting)**. Both streams must implement their endpoints in strict conformance with this contract.

---

## 1. Shared Identifiers & Types

All systems must conform to the following types:
* **`provider_id`**: UUID version 4 string format (validated via UUID regex or Pydantic's `UUID4`).
* **`service_id`**: UUID version 4 string format.
* **`datetime` format**: ISO 8601 string in UTC (e.g., `"2026-06-03T12:00:00Z"`).
* **`ProviderStatus`**: Enum string with exactly three allowed values:
  * `"pending_approval"` (default value upon onboarding registration)
  * `"approved"` (listing is visible in public directory lookup)
  * `"rejected"` (listing is hidden from public lookup)

---

## 2. Database Seam Contract

Both routers will interact with the database via the same shared SQLAlchemy models (defined in `SS-101` and `models.py`):

* **Provider Model Table**: `providers`
  * `id`: UUID (Primary Key)
  * `name`: String (Not Null)
  * `category`: String (Not Null)
  * `description`: String (Nullable)
  * `hourly_rate`: Float (Not Null, must be > 0)
  * `status`: String (Not Null, defaults to `"pending_approval"`)
  * `created_at`: DateTime (Defaults to UTC now)

---

## 3. API Contract Specifications

### A. Provider Onboarding (SS-102)
* **Path**: `POST /api/providers`
* **Request Body (JSON)**:
  ```json
  {
    "name": "string (min_length=1)",
    "category": "string (min_length=1)",
    "description": "string | null (optional)",
    "hourly_rate": "float (must be > 0)",
    "service_name": "string (min_length=1)",
    "service_description": "string | null (optional)"
  }
  ```
* **Success Response (201 Created)**:
  ```json
  {
    "id": "uuid",
    "name": "string",
    "category": "string",
    "description": "string | null",
    "hourly_rate": 50.0,
    "status": "pending_approval",
    "created_at": "ISO 8601 UTC datetime",
    "services": [
      {
        "id": "uuid",
        "name": "string",
        "description": "string | null"
      }
    ]
  }
  ```
* **Error Responses**:
  * `400 Bad Request` if `hourly_rate <= 0` or if name/category combination already exists.
  * `422 Unprocessable Entity` if required string inputs are missing, empty, or whitespace-only.

### B. Admin Vetting & Approval (SS-105)
* **Path**: `PUT /api/providers/{provider_id}/status`
* **Request Body (JSON)**:
  ```json
  {
    "status": "string (must be 'approved' or 'rejected')"
  }
  ```
* **Headers**:
  * `X-Admin-Key`: "string (must match ADMIN_API_KEY value in config)"
* **Success Response (200 OK)**:
  ```json
  {
    "id": "uuid",
    "name": "string",
    "status": "approved" // or "rejected"
  }
  ```
* **Error Responses**:
  * `400 Bad Request` if status value is not exactly `'approved'` or `'rejected'`, or if the provider is already in `'approved'` or `'rejected'` status (no state transition allowed from terminal states).
  * `401 Unauthorized` if `X-Admin-Key` header is missing.
  * `403 Forbidden` if `X-Admin-Key` header value is incorrect.
  * `404 Not Found` if `provider_id` does not exist.

---

## 4. Operational & Exception Handling Contracts

* **Unexpected Errors**: All uncaught exceptions (e.g. database disconnects) must return:
  * Code: `500 Internal Server Error`
  * Body: `{"detail": "Internal Server Error"}` (no internal stack traces leaked).
* **Logging Requirements**:
  * Stream A must emit log: `Provider registered successfully: id={provider_id}`.
  * Stream B must emit log: `Provider status updated: provider_id={provider_id}, status={status}`.
