# Module 3 Context Micro-Exercise

## 1. Catching wrong architectural approaches early
A classic example is starting to build a state synchronization logic using REST polling, only to realize that the scale of traffic will crush the database, and that a WebSockets or Event-Driven queue model is necessary.
What would have caught it earlier:
- Running a quick back-of-the-envelope calculation on database load.
- Presenting the proposal to the database/infrastructure team.
- Drawing a simple ASCII architecture flow diagram to show data paths.

## 2. Minimum document to get useful feedback before building
A 1-page design summary (frequently called a One-Pager or RFC draft) that contains:
1. **The Goal/Problem:** Clear, non-technical description of what problem is being solved.
2. **Proposed Solution:** High-level summary of the architecture and data flows.
3. **Tradeoffs & Alternatives Considered:** Exactly why we chose this over alternative options.
4. **Risks/Unresolved Questions:** Known boundaries where things might fail or need alignment.
