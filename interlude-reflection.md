# Interlude Reflection: Mars Climate Orbiter & Technical Communication

## 1. Implicit Assumptions in Our Technical Explanation
In our technical explanation document (`technical-explanation.md`), several implicit assumptions were present:
- **GraphQL Schema Location:** We assumed the reader knows how to find or run the server to access `app/schemas/graphql/` files. We didn't explicitly write the full paths or dependencies.
- **REST vs GraphQL Ports:** We assumed the reader understands that both systems run concurrently on different ports/endpoints under the same domain, which could lead to routing confusion if not explicitly mapped.
- **Tutorial Pre-requisites:** We assumed the reader is familiar with basic JavaScript or Python, which is needed to complete the tutorial at `graphql.org/learn`.

Making these assumptions explicit ensures that a newcomer like Priya can get started immediately without hitting undocumented walls.

## 2. Unverified Interfaces in Our Work
Often, we assume API responses, model constraints, and field names are "obvious." For example:
- Defining a date field without specifying the timezone rule (e.g. "always timezone-aware UTC").
- Stating a rate limit threshold (e.g., "100 requests") without specifying the duration (e.g., "per minute").
We can mitigate this by explicitly validating interfaces, comparing interpretation through documentation checks, and verifying contracts with automated tests.

## 3. Deciding Which "Trivial" Clarifications Are Worth Making
- **Clarification Metric:** If an ambiguity in a specification resides on a critical interface boundary (shared between different teams, systems, or services), the cost of misalignment is extremely high. Any shared boundary is always worth explicit clarification.
- **Rules of Thumb:** 
  1. Always specify units (e.g. milliseconds, UTC, bytes).
  2. Always specify ownership and fallback behavior.
  3. Avoid using undefined acronyms or local jargon.
