# Per-Task Context Bundles

This document defines the surgical context packages (bundles) for Tasks 3, 4, and 5 of the Team Collaboration Feature.

---

## Task 3: Create Comment & Thread Database Models

### Context Bundle

#### FILES TO READ:
1. [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py)
   * **Reason**: Shows the pattern for defining SQLAlchemy database models, including relationships, foreign keys, constraints, and datetime defaults.
   * **If Omitted**: The agent might use a different version of SQLAlchemy model definitions, incorrect datetime timezone-aware patterns, or map relationships incorrectly.
2. [database.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/database.py)
   * **Reason**: Shows the declarative `Base` model definition and database engine.
   * **If Omitted**: The agent might try to import `Base` from another package, or re-declare a separate database base instance.

#### FILES TO MODIFY:
* [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py)

#### EXPECTED OUTPUT:
* Modifying [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py) to add the following models:
  * `CommentThread`:
    * Table name: `comment_threads`
    * Attributes: `id` (Integer PK), `target_type` (String(50), index=True, nullable=False), `target_id` (Integer, index=True, nullable=False), `created_at` (DateTime timezone-aware, defaults to UTC).
    * Relationships: `comments` (one-to-many relationship with `Comment`, cascade delete).
  * `Comment`:
    * Table name: `comments`
    * Attributes: `id` (Integer PK), `thread_id` (Integer FK to `comment_threads.id` on delete CASCADE), `user_id` (String(255), index=True, nullable=False), `content` (Text, nullable=False), `created_at` (DateTime timezone-aware, defaults to UTC), `updated_at` (DateTime timezone-aware, defaults to UTC, with `onupdate` auto-trigger).
    * Relationships: `thread` (back-reference to `CommentThread`).

---

## Task 4: Implement Comment API Endpoints (Add, Edit, Fetch)

### Context Bundle

#### FILES TO READ:
1. [app/routers/teams.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/routers/teams.py)
   * **Reason**: Demonstrates FastAPI router conventions, dependency injection (`get_db`, `get_current_user`), transaction management (db session commit, refresh, rollback), and standard error raising.
   * **If Omitted**: The agent might write routes using inconsistent dependencies, manually build transaction scopes, or return plain dict errors instead of raising `HTTPException`.
2. [app/dependencies.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/dependencies.py)
   * **Reason**: Explains how protected routes use `get_current_user` to secure endpoints.
   * **If Omitted**: The agent might attempt to implement custom API key extraction or use incorrect dependencies.
3. [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py) (after Task 3 modifications)
   * **Reason**: Shows the structures of the `CommentThread` and `Comment` models to reference for queries and inserts.
   * **If Omitted**: The agent would not know what database attributes are available on the thread and comment instances.
4. [app/schemas/teams.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/schemas/teams.py)
   * **Reason**: Serves as a reference for Pydantic V2 schema configuration, specifically using `ConfigDict(from_attributes=True)` and field validator structures.
   * **If Omitted**: The agent might use legacy Pydantic V1 syntax or omit essential ORM configuration options.

#### FILES TO MODIFY:
* [main.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/main.py) (to register the new comments router)

#### EXPECTED OUTPUT:
* New file [app/schemas/comments.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/schemas/comments.py) containing Pydantic schemas:
  * `CommentCreate` (validates `content` text, non-empty, stripped).
  * `CommentUpdate` (validates `content` text, non-empty, stripped).
  * `CommentResponse` (returns ID, thread_id, user_id, content, created_at, updated_at).
* New file [app/routers/comments.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/routers/comments.py) exposing:
  * `POST /threads/{thread_id}/comments`: Adds comment to a thread (returns 201).
  * `PATCH /comments/{comment_id}`: Edits comment. Returns 403 Forbidden if user is not author.
  * `GET /threads/{thread_id}/comments`: Lists comments in a thread sorted by `created_at` ASC.
* Modify [main.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/main.py) to register the comment router under `app.include_router(comments.router)`.

---

## Task 5: Implement @Mention Regex Extraction Utility

### Context Bundle

#### FILES TO READ:
1. [app/services/links_service.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/services/links_service.py)
   * **Reason**: Shows the format for helper services, logger setup, and exception boundaries.
   * **If Omitted**: The agent might create a loose python function without proper logging, typing, or standard service class organization.

#### FILES TO MODIFY:
* None (this task creates new files only)

#### EXPECTED OUTPUT:
* New file [app/services/mention_service.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/services/mention_service.py) containing:
  * `extract_mentions(text: str) -> List[str]` function. Parses the input comment string and extracts unique @usernames (e.g. `@user_a` -> `user_a`). It must handle edge cases like trailing punctuation and lowercase normalization, returning only unique usernames.
