# Module 06 Execution Plan: Parallel AI Agent Coordination

This document records the coordination decisions, stream selections, and synchronization timeline for executing the vertical slices of the SkillSwap platform in parallel.

---

## 1. Core Coordination Decisions

* **Parallelism Strategy**: `isolated_branches`
  * *Rationale*: By isolating each agent in its own branch, we prevent merge conflicts and concurrent file writes (e.g. in `app/routers/providers.py` or database migrations) during development. The agents will work in isolation, relying strictly on the predefined interface contracts.
* **Synchronization Point Design**: `checkpoint_syncs`
  * *Rationale*: We define intermediate checkpoints to verify contract compliance early, preventing a "big bang" integration failure. If either agent deviates from the schemas, we catch the drift at the stubs phase rather than at final merge.

---

## 2. Selected Parallel Streams

We have selected two decoupled backend tasks that can run concurrently since their database models (from `SS-101`) are defined:

1. **Stream A: Provider Profile Onboarding (`SS-102`)**
   * *Responsibility*: Implement `POST /api/providers` to persist new provider profiles and service stubs.
   * *Branch*: `feature/ss-102-provider-onboarding`
2. **Stream B: Admin Vetting & Approval (`SS-105`)**
   * *Responsibility*: Implement `PUT /api/providers/{provider_id}/status` to allow admins to transition provider states.
   * *Branch*: `feature/ss-105-admin-vetting`

---

## 3. Synchronization Timeline & Milestones

```
Timeline:
Stream A (SS-102) ───[Create Router & Schemas]───┐
                                                 ├─► CHECKPOINT 1 (Interface Sync)
Stream B (SS-105) ───[Create Router & Schemas]───┘
                                                 
Stream A (SS-102) ───[DB Persistence Logic]──────┐
                                                 ├─► CHECKPOINT 2 (Merge & Integration)
Stream B (SS-105) ───[Vetting State Machine]─────┘
```

### Milestone 1: Interface Sync (Checkpoint 1)
* **Trigger**: Both agents have created their router files, declared endpoints, and defined their request/response Pydantic models.
* **Verification Gate**:
  * Ensure both routers use `prefix="/api/providers"`.
  * Verify Pydantic schema naming and field types match the contracts exactly.
  * Check that `provider_id` UUID formats and status enums are identical.

### Milestone 2: Merge & Integration (Checkpoint 2)
* **Trigger**: Both agents have completed route handlers, database transactions, input sanitization, and logging logic.
* **Verification Gate**:
  * Merge both branches into a shared `integration/provider-slices` branch.
  * Execute integrated API tests verifying end-to-end flow (Create provider -> Retrieve pending provider -> Approve provider -> Verify updated status).
