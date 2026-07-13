# Onboarding & Setup Guide: Team Collaboration Features

This guide explains how to get the Team Collaboration features running locally and how to execute the automated test suites.

---

## 1. Prerequisites
- Python 3.10+
- PostgreSQL database
- Local Python dependencies installed (`requirements.txt`)

---

## 2. Configuration & Environment Setup

1. Copy `.env.example` to create your local `.env` configuration file:
   ```bash
   cp .env.example .env
   ```

2. Verify that the `DATABASE_URL` is set to point to your PostgreSQL instance. For testing, the test suites force:
   ```env
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/upsk_sdf_test
   ```

3. Start your PostgreSQL server if it is not already running.

---

## 3. Database Table Creation

Database tables are automatically created on server startup using SQLAlchemy declarative metadata `Base.metadata.create_all(bind=engine)` inside `main.py`. 

No manual schema execution or migrations are required.

---

## 4. Running the Application locally

Start the development server using:
```bash
PYTHONPATH=. uvicorn main:app --reload --port 8000
```
The server will start on `http://127.0.0.1:8000`.

---

## 5. Running the Tests

To run the automated tests, execute the following commands in the project root:

### Run the entire test suite (224+ tests):
```bash
PYTHONPATH=. pytest
```

### Run only the new Capstone E2E Integration test:
```bash
PYTHONPATH=. pytest tests/test_capstone.py
```

### Run only the Permissions Matrix tests:
```bash
PYTHONPATH=. pytest tests/test_permissions.py
```

### Run only the WebSocket tests:
```bash
PYTHONPATH=. pytest tests/test_websockets.py
```
