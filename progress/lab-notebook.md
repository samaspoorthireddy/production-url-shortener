# System Design Fundamentals final Lab Notebook

This notebook provides the comprehensive, high-fidelity end-to-end verification proof of the URL Shortener application as mandated by the final demo script.

---

## 1. Health + Readiness Verification

### Positive Verification (Healthy State)
- **Liveness probe (`/health`)**:
  ```bash
  curl -fsS http://localhost:8000/health
  ```
  **Response**:
  ```json
  {"status":"healthy"}
  ```

- **Readiness probe (`/ready`)**:
  ```bash
  curl -fsS http://localhost:8000/ready
  ```
  **Response**:
  ```json
  {"status":"ready"}
  ```

### Negative Verification (Unready State)

#### A. Redis Cache Failure
We shut down the Redis cache database service using brew (`brew services stop redis`).
```bash
curl -i http://localhost:8000/ready
```
**Assertion Result**: Hitting the readiness endpoint instantly fails with `503 Service Unavailable`, correctly identifying the offline dependency without causing requests to hang:
```text
HTTP/1.1 503 Service Unavailable
date: Sun, 31 May 2026 13:41:14 GMT
server: uvicorn
content-length: 55
content-type: application/json
x-request-id: a712332c-94c8-402a-9f50-904dc24fdc3d

{"status":"unready","reason":"Redis connection failed"}
```

#### B. PostgreSQL Database Failure
We shut down the PostgreSQL database service using brew (`brew services stop postgresql@16`).
```bash
curl -i http://localhost:8000/ready
```
**Assertion Result**: Hitting the readiness endpoint instantly times out and returns `503 Service Unavailable`, preventing the ingress load balancers from routing traffic to this unready server container:
```text
HTTP/1.1 503 Service Unavailable
date: Sun, 31 May 2026 13:41:59 GMT
server: uvicorn
content-length: 58
content-type: application/json
x-request-id: 8bf97d53-33ae-4f78-8dcd-c4e8cafa3ef2

{"status":"unready","reason":"Database connection failed"}
```

#### C. Graceful Recovery
Upon starting both Redis and PostgreSQL services again, the readiness check automatically and instantly recovers to healthy status:
```text
HTTP/1.1 200 OK
date: Sun, 31 May 2026 13:42:07 GMT
server: uvicorn
content-length: 18
content-type: application/json
x-request-id: 6f64839e-2b0e-4af8-9c6a-971445822cd4

{"status":"ready"}
```

---

## 2. Link Creation (Protected)

- **Request**:
  ```bash
  curl -i -H "X-API-Key: API_KEY_A" -H "Content-Type: application/json" -d '{"long_url":"https://example.com"}' http://localhost:8000/links/
  ```
- **Response**:
  ```text
  HTTP/1.1 201 Created
  date: Mon, 01 Jun 2026 09:14:02 GMT
  server: uvicorn
  content-length: 181
  content-type: application/json
  x-request-id: e7812b1d-a01d-4b1a-add9-a11d63fc8c42

  {"id":57,"code":"OJvJow5E","long_url":"https://example.com","short_url":"http://localhost:8000/r/OJvJow5E","created_at":"2026-06-01T09:14:02.747126","created_by":"user_a","tags":[]}
  ```

---

## 3. Redirect Verification (Public)

- **Request**:
  ```bash
  curl -i http://localhost:8000/r/OJvJow5E
  ```
- **Response**:
  ```text
  HTTP/1.1 302 Found
  date: Mon, 01 Jun 2026 09:14:15 GMT
  server: uvicorn
  content-length: 0
  location: https://example.com
  x-request-id: 7bab8e0b-ac95-481e-8cec-05168239011f
  ```

---

## 4. Cache Invalidation & Update Proof

- **Step A: Update long URL (PATCH)**:
  ```bash
  curl -i -X PATCH "http://localhost:8000/links/57" -H "X-API-Key: API_KEY_A" -H "Content-Type: application/json" -d '{"long_url":"https://example.org"}'
  ```
  **Response**:
  ```text
  HTTP/1.1 200 OK
  x-request-id: 637b7b83-3c7e-4e38-9a4a-cb292da6704d

  {"id":57,"code":"OJvJow5E","long_url":"https://example.org","short_url":"http://localhost:8000/r/OJvJow5E","created_at":"2026-06-01T09:14:02.747126","created_by":"user_a","tags":[]}
  ```

- **Step B: Query Redirect again**:
  ```bash
  curl -i http://localhost:8000/r/OJvJow5E
  ```
  **Response**:
  ```text
  HTTP/1.1 302 Found
  location: https://example.org
  x-request-id: 633fdbec-819b-45d3-badb-00d91b67fc4d
  ```
  *Status: Verified. Stale cache was correctly invalidated and resolved instantly to the updated URL.*

---

## 5. Search + Pagination Verification

- **Request**:
  ```bash
  curl -i -H "X-API-Key: API_KEY_A" "http://localhost:8000/links/search?q=example&page=1&page_size=10"
  ```
- **Response**:
  ```text
  HTTP/1.1 200 OK
  content-type: application/json
  x-request-id: 583b2e30-b86b-49d2-bbb5-ceecec3af2a8

  {"results":[{"id":57,"code":"OJvJow5E","long_url":"https://example.org","short_url":"http://localhost:8000/r/OJvJow5E","created_at":"2026-06-01T09:14:02.747126","created_by":"user_a","tags":[],"click_count":0}],"metadata":{"page":1,"page_size":10,"total_records":1,"total_pages":1}}
  ```
