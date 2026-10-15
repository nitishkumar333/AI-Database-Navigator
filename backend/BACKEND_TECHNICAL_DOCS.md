# SQLNav — Backend Technical Documentation

> **Version:** 1.0.0 | **Framework:** FastAPI | **Language:** Python 3.11+
> **Entry Point:** `backend/main.py` | **Run:** `uvicorn main:app --reload`

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Folder Structure](#2-folder-structure)
3. [Configuration & Environment](#3-configuration--environment)
4. [Database Layer](#4-database-layer)
5. [Data Models (SQLAlchemy)](#5-data-models-sqlalchemy)
6. [API Routers](#6-api-routers)
7. [Services](#7-services)
8. [Utilities](#8-utilities)
9. [Key Data Flows](#9-key-data-flows)
10. [Security Architecture](#10-security-architecture)
11. [Caching Strategy](#11-caching-strategy)
12. [Rate Limiting](#12-rate-limiting)
13. [Dependency Map](#13-dependency-map)
14. [Where to Change Things](#14-where-to-change-things)

---

## 1. Architecture Overview

```
                    FastAPI (main.py)
                          |
         +----------------+----------------+
         |                |                |
     Routers          Services          Utils
     /api/*         SQL Agent         Security
         |           Validator         DB Mgr
         |           Rate Lim.         SQL Guard
         |           Redis             Prompts
         v
    SQLAlchemy ORM
         |
    +----+----+
    |         |
  App DB   User DB
 (Postgres) (Postgres)
```

- **App Database** — stores users, DB connections (with encrypted passwords), knowledge bases, query history, conversations.
- **User's Database** — the target PostgreSQL database that users connect to and query via NL to SQL.
- **Redis** — caches schema introspection, table lists, knowledge base groups, suggestions, and rate limit sliding windows.
- **LangGraph + Gemini** — the core NL-to-SQL agent with persistent conversation memory stored in SQLite (`checkpoints.sqlite`).

---

## 2. Folder Structure

```
backend/
├── main.py                      # FastAPI app entry point, router registration, startup
├── requirements.txt             # Python dependencies (pip)
├── .env                         # Environment variables (not committed)
├── .env.example                 # Template for environment variables
├── Dockerfile                   # Container build instructions
├── .dockerignore
├── seed_shop.py                 # Script to seed demo PostgreSQL data
├── checkpoints.sqlite           # LangGraph conversation memory (SQLite WAL)
|
└── app/
    ├── __init__.py
    ├── config.py                # Pydantic Settings (reads .env)
    ├── database.py              # SQLAlchemy engine, session, init_db()
    |
    ├── models/                  # SQLAlchemy ORM table definitions
    |   ├── __init__.py
    |   ├── user.py              # User table
    |   ├── connection.py        # DBConnection table
    |   ├── knowledge.py         # KnowledgeBase table
    |   ├── query_history.py     # QueryHistory table
    |   └── conversation.py      # Conversation + ConversationMessage tables
    |
    ├── routers/                 # FastAPI APIRouter modules (HTTP endpoints)
    |   ├── __init__.py
    |   ├── auth.py              # POST /register, POST /login, GET /me, GET /onboarding-status
    |   ├── connections.py       # CRUD for DB connections
    |   ├── schema.py            # GET tables, columns, preview from user's DB
    |   ├── knowledge.py         # CRUD for knowledge base groups
    |   ├── query.py             # POST /chat (NL to SQL)
    |   ├── history.py           # GET query history
    |   ├── conversations.py     # CRUD for chat conversations
    |   └── suggestions.py       # AI-generated query suggestions
    |
    ├── services/                # Business logic / AI integrations
    |   ├── __init__.py
    |   ├── sql_agent.py         # SQLAgent: thin entry point for one agent turn
    |   ├── agent/               # Agent graph (compiled once), tools, prompt, budgets
    |   ├── validate_sql.py      # SafeSqlExecutor: AST validation (sqlglot) + EXPLAIN + read-only transaction sandbox
    |   ├── rate_limiter.py      # Sliding-window rate limiter (Redis sorted sets)
    |   └── redis_client.py      # Redis wrapper (get/set/delete with JSON auto-encode)
    |
    └── utils/                   # Cross-cutting helpers
        ├── __init__.py
        ├── security.py          # JWT, Argon2, Fernet encryption, get_current_user
        ├── db_manager.py        # SQLAlchemy engine cache, schema context builder, table caching, SQL refinement
        ├── prompts.py           # LLM prompt templates (suggestions)
        └── sql_guard.py         # SQL allowlist/blocklist regex + table name sanitizer
```

---

## 3. Configuration & Environment

### `app/config.py`

Uses `pydantic-settings` `BaseSettings`. All env vars are read from `.env`.

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `SQLNav` | Application name |
| `SECRET_KEY` | `change-this-...` | JWT signing secret — must change in prod |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | JWT token lifetime |
| `DATABASE_URL` | `""` | App's own PostgreSQL URL |
| `GEMINI_API_KEY` | `""` | Google Gemini API key for LLM calls |
| `ENCRYPTION_KEY` | `""` | Fernet key for encrypting DB passwords at rest; auto-generated if empty |
| `REDIS_HOST` | `localhost` | Redis host (read in `redis_client.py` from `os.getenv`) |
| `REDIS_PORT` | `6379` | Redis port |
| `GUEST_DB_HOST` | `localhost` | Hostname for guest demo database connection |
| `GUEST_DB_PORT` | `5432` | Port for guest demo database connection |
| `GUEST_DB_NAME` | `shop` | Database name for guest demo connection |
| `GUEST_DB_USER` | `postgres` | Username for guest demo connection |
| `GUEST_DB_PASSWORD` | `password` | Password for guest demo connection |

**To add a new config variable:** Add a new field to `Settings` class in `config.py`, then access via `get_settings()`.

---

## 4. Database Layer

### `app/logging_setup.py`

One handler and format for the backend's own terminal lines, `HH:MM:SS LEVEL [area] message`. Areas: `agent` (`services/agent/trace_log.py`, every LLM and tool call; `AGENT_LOG_LEVEL`), `jobs` (`services/schema_index/job_log.py`, profile/index/describe steps; `JOB_LOG_LEVEL`), and every other `app.*` module at WARNING only. `get_logger(area)` returns an area's logger; `configure_logging()` runs at startup and is idempotent. The `app.*` handler is skipped when the root logger is already configured (evaluation runs), so nothing prints twice.

### `app/database.py`

```python
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():   # FastAPI dependency - yields a session, closes it after
def init_db():  # Called on startup - creates all tables via Base.metadata.create_all(), then _migrate()
```

- **App DB** is a single PostgreSQL instance configured via `DATABASE_URL`.
- `_migrate()` holds idempotent fixes `create_all` can't make on existing tables: it switches the `knowledge_base` and `query_history` foreign keys to `ON DELETE CASCADE`, and links conversations to the connections they used before `conversation_connections` existed (from the agent's checkpoint thread names `user:connection:conversation`).
- **User DBs** are separate connections managed by `db_manager.py` with an in-memory LRU engine cache.
- `init_db()` is called in `main.py`'s `@app.on_event("startup")`. It imports all model modules to register them with `Base` before calling `create_all`.

---

## 5. Data Models (SQLAlchemy)

### `app/models/user.py` — `User`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `email` | String UNIQUE | Login identifier |
| `username` | String UNIQUE | Display name |
| `hashed_password` | String | Argon2 hash via passlib |
| `created_at` | DateTime | UTC, set on insert |

### `app/models/connection.py` — `DBConnection`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | Integer FK to users | Ownership |
| `name` | String | Display label (user-defined) |
| `host` | String | PostgreSQL host |
| `port` | Integer | Default 5432 |
| `db_name` | String | Target database name |
| `username` | String | DB login |
| `encrypted_password` | String | Fernet-encrypted DB password |
| `created_at` | DateTime | UTC |

### `app/models/knowledge.py` — `KnowledgeBase`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `name` | String | KB group name |
| `tables` | JSON | List of table names to include |
| `connection_id` | Integer FK to db_connections | Cascade delete |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC, auto-updated |

### `app/models/schema_profile.py` — `SchemaProfileRecord` + `SchemaAnnotation`

See [Schema Profiling](#appservicesschema_index--schema-profiling-ai-context). `schema_profiles` holds the latest profile per connection (unique `connection_id`); `schema_annotations` holds descriptions, unique per `(connection_id, table_name, column_name)` with `column_name = ""` for the table itself.

### `app/models/query_history.py` — `QueryHistory`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | Integer FK to users | |
| `connection_id` | Integer FK to db_connections | Cascade delete |
| `nl_query` | Text | Original natural language question |
| `generated_sql` | Text | SQL generated by agent |
| `success` | Boolean | Did the query execute successfully? |
| `error_message` | Text | Error if success=False |
| `created_at` | DateTime | UTC |

### `app/models/conversation.py` — `Conversation` + `ConversationMessage` + `ConversationConnection`

**`Conversation`**

| Column | Type | Notes |
|---|---|---|
| `id` | String PK | UUID provided by frontend |
| `user_id` | Integer FK to users | |
| `name` | String | Display title |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC, auto-updated |

**`ConversationConnection`** (`conversation_connections`): every connection a conversation queried at least once, written by `POST /api/query`. Primary key `(conversation_id, connection_id)`, both foreign keys cascade, plus `first_used_at`.

**`ConversationMessage`**

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `conversation_id` | String FK to conversations | Cascade delete |
| `role` | String | "user" or "assistant" |
| `content` | Text | Message text |
| `message_type` | String | "text" or "result" |
| `metadata_json` | Text | JSON blob: generated_sql, columns, rows, success, error |
| `query_id` | String | Groups a user+assistant message pair |
| `created_at` | DateTime | UTC |

**To add a new model:** Create a new file in `app/models/`, define the class extending `Base`, then add an import to `init_db()` in `database.py`.

---

## 6. API Routers

All routers are mounted in `main.py` via `app.include_router(...)`.

### `app/routers/auth.py` — prefix `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/register` | No | Register new user. Returns UserResponse. Validates email/username uniqueness. |
| POST | `/login` | No | Login. Returns JWT access_token. |
| POST | `/guest-login` (or `/guest`) | No | One-click login to the shared guest account (created with its shop DB connection, knowledge base and demo conversations on first use). Returns JWT access_token. |
| GET | `/me` | JWT | Returns current user info (including `is_guest: boolean`). |
| GET | `/onboarding-status` | JWT | Returns has_connection, has_knowledge_base, onboarding_complete. Used by frontend router. |

### `app/routers/connections.py` — prefix `/api/connections`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/` | JWT | Create new DB connection. Tests connection first. Encrypts password with Fernet. |
| GET | `/` | JWT | List all connections for current user. |
| POST | `/test` | JWT | Test a connection without saving. |
| DELETE | `/{conn_id}` | JWT | Delete the connection and everything stored about it (`services/connection_cleanup.py`): knowledge bases, query history, schema profile and descriptions, retrieval index, every conversation that queried it (messages and agent checkpoint threads included), cached engine, Redis keys and in-process schema caches. Returns `deleted_conversations` (ids) so the UI can drop them. |

**To add a new connection field:** Update `DBConnection` model, `ConnectionCreate`, and `ConnectionResponse` schemas in `connections.py`.

### `app/routers/schema.py` — prefix `/api/schema`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/{conn_id}/tables` | JWT | Lists all tables with column counts. No cache. |
| GET | `/{conn_id}/tables/{table_name}/columns` | JWT | Column info + PK + FK. Redis cached. |
| GET | `/{conn_id}/tables/{table_name}/preview` | JWT | First 10 rows of a table. Redis cached. |
| GET | `/{conn_id}/profile` | JWT | Schema-profile status and each table's row count and description. |
| POST | `/{conn_id}/profile/refresh` | JWT | Re-profile in the background (`{"describe": bool}` optional). Returns 202. |
| GET | `/{conn_id}/tables/{table_name}/details` | JWT | Descriptions (with source: `generated` / `user` / `comment`), sample values, formats, joins. 404 until profiled. |
| PUT | `/{conn_id}/tables/{table_name}/description` | JWT | Set the table description the agent sees; `""` resets it. |
| PUT | `/{conn_id}/tables/{table_name}/columns/{column}/description` | JWT | Same for a column. |

Redis cache keys:
- `table_schema:user:{uid}:connection:{cid}:table:{name}`
- `preview:user:{uid}:connection:{cid}:table:{name}`

### `app/routers/knowledge.py` — prefix `/api/knowledge`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/user/groups/all` | JWT | All KB groups across all connections for current user. Redis cached. |
| GET | `/{conn_id}/groups` | JWT | KB groups for a specific connection. Redis cached. |
| POST | `/{conn_id}/group` | JWT | Create a KB group. Name must be unique per connection. Invalidates cache. |
| DELETE | `/group/{group_id}` | JWT | Delete a KB group. Invalidates cache. |

Redis cache keys:
- `kb:user:{uid}:connections:all`
- `kb:user:{uid}:connection:{cid}:groups`

### `app/routers/query.py` — prefix `/api/query`

This is the **core** router for NL-to-SQL.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/chat` | JWT | Main NL-to-SQL endpoint. Accepts question, connection_id, knowledge_base_id, conversation_id, query_id. Runs rate limit, resolves connection, builds schema context, runs SQL agent, saves to history + conversation. |

**ChatRequest schema:**

```python
class ChatRequest(BaseModel):
    question: str
    connection_id: int | None = None       # Falls back to user's first connection
    knowledge_base_id: int | None = None   # Scopes schema to KB tables
    conversation_id: str | None = None     # UUID from frontend
    query_id: str | None = None            # UUID for grouping messages
```

**Response shape:**

```json
{
  "success": true,
  "question": "...",
  "generated_sql": "SELECT ...",
  "columns": ["col1", "col2"],
  "rows": [{ "col1": "val1" }],
  "response_text": "Here are the results...",
  "connection_name": "My DB",
  "connection_id": 1
}
```

### `app/routers/history.py` — prefix `/api/history`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | JWT | List history (optional ?connection_id=&limit=50). |
| GET | `/{history_id}` | JWT | Get single history entry. |

### `app/routers/conversations.py` — prefix `/api/conversations`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | JWT | List all conversations with message counts, ordered by updated_at DESC. |
| POST | `/` | JWT | Create conversation (idempotent - returns existing if same UUID). |
| GET | `/{conversation_id}` | JWT | Full conversation detail with all messages. |
| PUT | `/{conversation_id}` | JWT | Rename conversation. |
| DELETE | `/{conversation_id}` | JWT | Delete conversation and all messages (cascade). |

### `app/routers/suggestions.py` — prefix `/api/suggestions`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/initial` | JWT | Generate 4 initial query suggestions based on schema. Redis cached (1h). Supports force_refresh. |
| POST | `/conversation` | JWT | Generate 3 follow-up suggestions based on conversation history. Not cached. |

Both use `gemini-2.5-flash` with structured output (`SuggestionList`) for JSON-typed responses.

---

## 7. Services

### `app/services/guest_service.py` — Guest Account

A single, shared guest account (`guest@sqlnav.demo`, username `guest`) used by everyone who clicks "Login as Guest". It is an ordinary account (conversations, history and knowledge bases are stored like any other user's) except:
- It has no usable password (random hash), so it is only reachable via `/api/auth/guest-login`.
- Its only connection is the PostgreSQL `shop` database (`GUEST_DB_*` settings). On every guest login the connection is re-created if missing and synced to the current settings. `POST /api/connections`, `POST /api/connections/test` and `DELETE /api/connections/{id}` return 403 for the guest.
- The `@sqlnav.demo` domain and the username `guest` are reserved at registration.

On first creation it also gets the `"Shop Catalog & Orders"` knowledge base (all 9 tables) and 3 demo conversations with query history; later logins never re-seed. `is_guest(user)` (domain check) also matches the older per-login `guest_{uid}@sqlnav.demo` accounts.

### `app/services/sql_agent.py` + `app/services/agent/` — The Core AI System

`SQLAgent` (`sql_agent.py`) is a thin wrapper: it bundles one connection's
context and runs a turn of the agent graph in `services/agent/`. The graph is
compiled **once per process** (one for production with the Postgres
checkpointer, one for evaluation without it); everything connection-specific
travels in an `AgentContext` passed as `graph.invoke(..., context=ctx)` and is
never written to a checkpoint.

```
User Question
     |
     v
link (schema linking; only when the prompt holds the table list, see below)
     |
     v
agent (LLM with schema in system prompt + 5 tools) <--------------------+
     |                                                                   |
     +-- tool calls --> tools node (budget check, parallel execution) ---+
     |                    search_schema    hybrid search over tables/columns (retrieval index)
     |                    describe_tables  full detail + FK join paths
     |                    find_values      how a mentioned value is stored
     |                    run_sql          exploratory, <=20 rows + row count
     |                    submit_answer    final query, up to 200 rows -> ends the search
     |
     +-- answer submitted --> production: agent writes the reply --> END
     |                        evaluation: END (the SQL is what gets scored)
     +-- no tool calls -----> END (greeting / clarifying question)
     v
Return { success, generated_sql, columns, rows, assumptions, answer_source, response_text }
```

**Schema in the prompt**: when the full schema of the allowed tables fits
`AGENT_FULL_SCHEMA_MAX_CHARS` (32k chars, ~8k tokens) it goes in the system
prompt and the agent can submit straight away. Above that, the prompt holds
only a table list (name, approximate rows, one-line description;
`render.render_catalog`, capped at ~6k tokens with shorter fallbacks) and the
agent reads columns with `describe_tables`, so the prompt stays bounded however
large the database is. The choice is made per request in `SQLAgent.__init__`.

**Schema linking** (table-list prompt only): before the first LLM call the
`link` node searches the schema with the question (plus the previous question
for short follow-ups), keeps the strongest foreign-key-connected group of
tables, adds the bridge tables that join them (approximate Steiner tree on the
FK graph) and any table holding a value the question mentions, and appends
them in full to this turn's system prompt (`SCHEMA_LINK_MAX_TABLES` tables,
`SCHEMA_LINK_MAX_CHARS` chars; compact detail before dropping a table). Most
questions are then answered with a single `submit_answer`; `describe_tables`
is only needed for tables linking missed. If linking fails or finds nothing,
the turn proceeds with the plain table list.

**Budgets** (`agent/state.py` `Budget`): 8 tool calls and 6 SQL executions per
turn, kept in graph state. Calls beyond them are refused; once a budget is used
up the next model call may only call `submit_answer` (forced `tool_choice`,
falling back to a submit-only binding where a provider rejects it). A model
that explores but replies without submitting is asked to submit once. After 2
forced submits without a valid answer the turn ends and the last successful
`run_sql` query is returned (`answer_source="exploration"`) with an
explanation instead of an error.

**Parallel tool calls** run on a shared thread pool; SQL from them is limited
per engine by a semaphore (`tools.sql_slot`) because user engines have a pool
of only 2 + 3 connections.

| File | Role |
|---|---|
| `sql_agent.py` | `SQLAgent(engine, schema_context, *, mode, llm, schema_view, budget)` and `run_query(...)`; result + evaluation trace. |
| `agent/graph.py` | Nodes, routing, budgets, history replay (whole current turn + 20 earlier messages, unanswered tool calls stripped), compiled graphs, checkpointer. |
| `agent/tools.py` | Tool schemas the model sees (`TOOL_SCHEMAS`) and their implementations (`run_tool(ctx, name, args)`). |
| `agent/prompts.py` | System prompt: workflow, query rules, schema legend, PostgreSQL pitfalls. |
| `agent/state.py` | `AgentState`, `AgentContext`, `Budget`. |

**To change the LLM model:** set `LLM_PROVIDER` / `*_MODEL` (see `llm_factory.py`).

**To change the system prompt:** edit `agent/prompts.py`.

**To add a new tool:** add an args model + entry in `TOOL_SCHEMAS` and an
implementation in `_IMPLEMENTATIONS` (`agent/tools.py`); add its name to
`SQL_TOOLS` if it runs user SQL.

---

### `app/services/schema_index/` — Schema Profiling (AI context)

What the agent reads about a database. Replaces the bare column list from
`get_schema_context` once a connection has been profiled.

| Module | Role |
|---|---|
| `profiler.py` | `profile_database(engine)`: tables, columns, keys and comments from `pg_catalog`; null fraction, distinct count, most-common values and ranges from `pg_stats` (no table scans); a `LIMIT 500` sample for tables without statistics; format detection for text columns (`'YYYYMM'`, dates, numbers or zero-padded codes stored as text); inferred foreign keys (name match confirmed by a containment probe). `schema_fingerprint(engine)` is the cheap change check (also used to match twin connections). |
| `render.py` | `render_schema(profile, tables, descriptions)`: one compact line per column (`name type PK -> t.c -- description; values: ...; format; range`). Falls back to a compact level above ~60k chars. |
| `job_log.py` | Terminal log of the background jobs, one `[jobs]` line per step: `PROFILE` start/done/reused/failed, `INDEX` ready (with the reason, mode and doc/value counts; silent when nothing changed), `DESCRIBE` start, progress per chunk of 5 (marks knowledge-base tables), failed tables, rate-limit waits and the final summary, `SCHEMA` changes. `JOB_LOG_LEVEL`: INFO (default), WARNING (problems only), ERROR (off). |
| `describer.py` | One structured LLM call per table: what a row represents + ≤20-word column descriptions. |
| `service.py` | Background jobs (2-thread pool, Redis lock per connection), `build_schema_context(db, conn, engine, tables)` used by `/api/query/chat` and suggestions, `build_schema_view(...)` for the agent's schema tools, staleness checks, and description editing. |
| `retriever.py` | `SchemaView`: the agent's scoped view of the schema (profile + descriptions, limited to the allowed tables; a minimal inspector-based profile before profiling finishes). `search` (behind `search_schema`) uses the retrieval index when the connection has one, else keyword scoring; `link` is schema linking (see above). |
| `join_graph.py` | `JoinGraph`: shortest join paths between tables over declared + inferred foreign keys (BFS), shown by `describe_tables`; `bridge_tables` connects a set of tables (greedy Steiner tree). |
| `documents.py` | What gets indexed: one document per table (name split into words, summary, comment, key and main columns) and per column (table + column names, type/format, description, comment, top values), each with an embedding text and a trigram text; plus every value of low-cardinality text columns (≤ `SCHEMA_VALUE_INDEX_MAX_DISTINCT` distinct, read with a bounded `SELECT DISTINCT` when the statistics don't cover them). |
| `index_store.py` | Storage in the app database: `schema_index_docs` (trigram GIN index + `vector` column), `schema_index_values` (trigram GIN index), `schema_index_state`. `search` ranks documents with three lists fused by reciprocal rank fusion in one SQL query: cosine distance to the question's embedding, trigram `word_similarity` of the question's terms, and stored values the question mentions (`strict_word_similarity`). Vector search is exact (one connection's few thousand rows), not HNSW, so scoping by connection and allowed tables never loses rows. |
| `indexer.py` | `update_index(key, profile, descriptions, source_engine)`: incremental, only re-embeds documents whose text changed and reuses embeddings any index already has for the same text and model. `HybridIndex`: the search handle `SchemaView` uses; it adds the keyword ranking as a fourth RRF list. |
| `../embeddings.py` | `JinaEmbedder` (Jina AI embeddings API, `retrieval.passage` / `retrieval.query`, batched, retried on 429/5xx); `get_embedder()` is None without `JINA_API_KEY`. |

Lifecycle:
1. Creating a connection (UI or guest sign-up) schedules a profile job; connections that predate profiling get one on their first chat. Until it finishes, the agent gets the basic schema; requests never wait.
2. Another connection to the same host/port/database with the same login and an identical schema donates its profile and generated descriptions (guest accounts all share the demo DB, so it is described once, not per guest).
3. Every `SCHEMA_CHECK_INTERVAL_S` (checked when the connection is used) the catalog fingerprint is compared; a change triggers a re-profile. A re-profile can also be requested any time (`POST /api/schema/{id}/profile/refresh`, the "Re-profile" button in the table explorer). Tables whose structure changed are re-described; unchanged tables keep their descriptions.
4. Descriptions with source `user` (edited in the table explorer's Columns tab) are never overwritten. Precedence: user > database COMMENT > generated.
5. Describing runs until every table is described, 5 tables at a time. Before each chunk the order is recomputed: tables of the connection's knowledge bases first, then the most connected tables (foreign keys in and out), then the largest. So before any knowledge base exists the central tables (`users`, `orders`, ...) go first, and a knowledge base saved mid-run jumps the queue at the next chunk. Saving a knowledge base starts a describe-only job (`schedule_describe`) when none is running. A rate limit pauses 30/60/120 s, then the run stops as `partial`; a table that fails is skipped until the next run. The job lock is extended while it runs.
6. The retrieval index (key `conn:<id>`) is updated after profiling, after every `SCHEMA_DESCRIBE_MAX_TABLES` (50) new descriptions, as soon as all knowledge-base tables are described, and at the end of describing, and in the background after a description edit; a connection profiled before indexing existed is indexed on its next chat. Deleting the connection deletes its index.

Retrieval degrades step by step: no `JINA_API_KEY` (or an embedding outage) → trigram + value search; no pgvector in the app database or `SCHEMA_RETRIEVAL_ENABLED=false` → keyword search over the profile. The app database needs the `vector` extension (`docker-compose.yml` builds it inline: `postgres:16-alpine` + pgvector); `pg_trgm` ships with Postgres. Index status is part of `GET /api/schema/{id}/profile` (`index`).

Storage: `schema_profiles` (one row per connection: status, profile JSON, `version` for cache invalidation, which tables are described at which structure hash) and `schema_annotations` (one row per table/column description). Both cascade on connection delete. Rendered context is cached in-process per `(connection, version, tables)`. The index tables (`schema_index_*`) are created on first use.

### `app/services/validate_sql.py`

**Class: `SafeSqlExecutor`**

Validates and executes LLM-generated read-only SQL queries against user databases using a three-layer defense-in-depth model:

```
               Incoming SQL String
                        |
                        v
   Layer 1: AST Structural & Security Check (sqlglot)
   - Single statement only
   - Allowed root: SELECT, UNION, INTERSECT, EXCEPT (CTEs supported)
   - Deep traversal blocklist: INSERT, UPDATE, DELETE, MERGE, DROP, etc.
   - Forbidden functions: pg_sleep, set_config, dblink, lo_*, etc.
                        | (Passed)
                        v
   Layer 2: Schema Validation via EXPLAIN
   - Executes EXPLAIN <sql> against the database
   - Verifies tables, columns, aliases, types exist without running query
                        | (Passed)
                        v
   Layer 3: Transaction-Level Sandboxed Execution
   - SET TRANSACTION READ ONLY (engine-level write lock)
   - SET LOCAL statement_timeout = 10000 (10s runaway query protection)
   - Fetch max_rows + 1 (50 rows) for memory-safe truncation detection
                        |
                        v
               QueryResult Dataclass
   - .to_llm_string() serializes compact JSON + truncation advice
```

**Dataclasses:**

- **`ValidationResult`**: `sql: str`, `is_valid: bool`, `reason: str`, `validation_query: Optional[str] = None` (the `EXPLAIN` query).
- **`QueryResult`**: `sql: str`, `success: bool`, `columns: List[str]`, `rows: List[Dict[str, Any]]`, `truncated: bool`, `error: Optional[str]`.
  - `to_llm_string()`: Produces compact JSON (`columns`, `row_count`, `rows`) safely serializing Decimal, datetime, UUID, etc. If `truncated=True`, appends a note: `"Output truncated to the first {len(rows)} rows. Add a LIMIT or a more specific filter."`

**Defense-in-Depth Layers:**

1. **Layer 1 — AST Check (`_check_structure` using `sqlglot`)**:
   - Parses with `sqlglot.parse(sql, read="postgres")`.
   - Rejects empty queries, syntax errors, and multi-statement queries (blocks semicolon chaining).
   - Root allowlist (`_ALLOWED_ROOTS`): Statement root must be `exp.Select`, `exp.Union`, `exp.Intersect`, or `exp.Except` (`WITH ... SELECT` CTEs parse as Select roots).
   - Deep node inspection (`_FORBIDDEN_NODES`): Recursively inspects every node to block data modification or locking anywhere in the query: `Insert`, `Update`, `Delete`, `Merge`, `Create`, `Drop`, `Alter`, `AlterTable`, `TruncateTable`, `Command`, `Copy`, `Set`, `Into`, `Lock` (blocks e.g. `WITH d AS (DELETE ...) SELECT ...`, `SELECT ... INTO`, `FOR UPDATE`).
   - Dangerous functions blocklist (`_FORBIDDEN_FUNCTIONS` & `_FORBIDDEN_FUNCTION_PREFIXES`): Blocks `pg_sleep`, `pg_sleep_for`, `pg_sleep_until`, `set_config`, `nextval`, `setval`, `pg_terminate_backend`, `pg_cancel_backend`, `pg_reload_conf`, and prefixes `pg_read_`, `pg_ls_`, `pg_advisory_`, `lo_`, `dblink`, `query_to_`.

2. **Layer 2 — Schema Validation via EXPLAIN (`_check_against_schema`)**:
   - Runs `EXPLAIN {sql}` inside a read-only transaction.
   - Verifies all table and column names against the live PostgreSQL catalog without scanning or reading table rows.

3. **Layer 3 — Sandboxed Execution (`_execute` & `_read_only_connection`)**:
   - Runs in a managed transaction context manager:
     - `SET TRANSACTION READ ONLY` — hard database-engine enforcement against data mutation.
     - `SET LOCAL statement_timeout = {int(self.timeout_ms)}` (default 10,000ms / 10s) — terminates expensive or locking operations.
   - Result fetching: Fetches `self.max_rows + 1` (default 50) to detect whether results were truncated, preventing unbounded memory consumption.
   - Driver error sanitization (`_clean_error`): Extracts `getattr(exc, "orig", exc)` to strip verbose SQLAlchemy wrapper noise and return concise database driver errors.

> **Note:** Helper functions previously located in this module (`refine_sql_from_markdown`, `get_all_table_names`, `get_schema_context`) are now centralized in `app.utils.db_manager`.

---

### `app/services/rate_limiter.py`

Sliding-window rate limiter using Redis sorted sets.

**Config constants (top of file):**

```python
RATE_LIMIT_MAX_REQUESTS = 3    # max requests allowed
RATE_LIMIT_WINDOW_SECS  = 90   # sliding window in seconds
```

**`check_rate_limit(user_id, client_ip)`** enforces two independent limits:
1. Per-IP: `rate_limit:chat:ip:{ip}` — prevents multi-account abuse.
2. Per-User: `rate_limit:chat:user:{uid}` — prevents VPN/proxy abuse.

Raises `HTTP 429` with `Retry-After` header when limit exceeded.

**To change limits:** Modify `RATE_LIMIT_MAX_REQUESTS` and `RATE_LIMIT_WINDOW_SECS`.

---

### `app/services/redis_client.py`

Simple Redis wrapper that auto-serializes/deserializes JSON:

```python
redis_client.set(key, value, ex=3600)  # value can be dict/list/str
redis_client.get(key)                   # auto-parses JSON on return
redis_client.delete(key)
```

Uses `REDIS_HOST` / `REDIS_PORT` from environment variables.

**Note:** `redis_client.client` exposes the raw `redis.Redis` instance (needed for sorted-set operations in rate_limiter.py).

---

## 8. Utilities

### `app/utils/security.py`

| Function | Description |
|---|---|
| `hash_password(password)` | Argon2 hash via passlib CryptContext |
| `verify_password(plain, hashed)` | Verify Argon2 hash |
| `create_access_token(data, expires_delta)` | Create JWT, default 24h expiry |
| `decode_token(token)` | Decode + verify JWT, raise 401 on failure |
| `encrypt_value(value)` | Fernet-encrypt a string (used for DB passwords) |
| `decrypt_value(encrypted)` | Fernet-decrypt a string |
| `get_current_user(token, db)` | FastAPI dependency — decodes JWT, loads User from DB |

The Fernet key is loaded from `settings.ENCRYPTION_KEY`. If empty, a new key is auto-generated and printed as a warning.

**Password security:** User passwords use Argon2 (one-way), DB credentials use Fernet (reversible, needed for connection).

---

### `app/utils/db_manager.py`

| Function | Description |
|---|---|
| `get_user_engine(connection)` | Returns (or creates) a SQLAlchemy engine for a user's DB. Cached in TTLCache(maxsize=100, ttl=3600). Decrypts password from connection object. |
| `test_connection(host, port, db_name, username, password)` | Test DB connectivity (runs SELECT 1). Returns `{ success, message }`. |
| `remove_engine(conn_id)` | Disposes and removes cached engine for a connection (called on delete). |
| `refine_sql_from_markdown(text_input)` | Strips markdown code blocks (````sql`), flattens newline and tab escape characters to spaces, normalizes punctuation spacing, and ensures trailing semicolon. |
| `get_all_table_names(engine)` | Introspects DB table names via `sqlalchemy.inspect`. Redis cached for 1h (`tables:{url_md5}`). |
| `get_schema_context(engine, table_names)` | Introspects columns, types, PRIMARY KEYs, and foreign keys (`FOREIGN KEY (...) REFERENCES ...(...)`) to build a formatted schema string for LLM system prompts. Redis cached for 1h (`schema:{url+tables_md5}`). |

The engine cache (`_engine_cache`) prevents creating new connection pools on every request.

---

### `app/utils/prompts.py`

Two lambda prompt templates:

- `initial_suggestions_prompt(schema_context)` — asks LLM for 4 varied questions about the DB.
- `conversation_suggestions_prompt(schema_context, history_text)` — asks LLM for 3 follow-up questions based on recent conversation.

**To change suggestion prompts:** Edit these lambda functions directly.

---

### `app/utils/sql_guard.py`

- `validate_sql(sql)` — blocklist check + SELECT-only enforcement + auto-adds `LIMIT 1000`. Lightweight regex guard used for table preview queries.
- `sanitize_table_name(name)` — strips non-alphanumeric/underscore characters to prevent injection in table name interpolation (used in `schema.py` preview endpoint).

---

## 9. Key Data Flows

### NL to SQL Query Flow

```
Frontend POST /api/query/chat
         |
         v
1. check_rate_limit(user_id, client_ip)         [rate_limiter.py]
         |
         v
2. Resolve DBConnection from connection_id      [DB query, falls back to first connection]
         |
         v
3. get_user_engine(conn)                        [db_manager.py - TTLCache hit or create]
         |
         v
4. Resolve table_filter from knowledge_base_id  [DB query for KnowledgeBase.tables list]
         |
         v
5. get_all_table_names(engine)                  [db_manager.py - Redis cached]
         |
         v
6. build_schema_context(...) + build_schema_view(...)  [schema_index/service.py - cached per profile version]
         |
         v
7. SQLAgent(engine, schema_context, schema_view=...).run_query()  [sql_agent.py -> agent/graph.py]
         |
   7a. link node: table-list prompt only -> retrieved tables added in full
         |
   7b. agent node: LLM with schema in the system prompt and 5 tools bound
         |
   7c. Optional exploration: search_schema / describe_tables / find_values / run_sql,
         |    several per turn, run in parallel within the per-turn budget
         |
   7d. submit_answer(sql, assumptions) -> SafeSqlExecutor.run(sql)  [validate_sql.py]
         |    - Layer 1: sqlglot AST validation (_check_structure)
         |    - Layer 2: Schema validation via EXPLAIN in read-only tx (_check_against_schema)
         |    - Layer 3: Execute in read-only tx with 10s timeout (_execute)
         |    (an error goes back to the LLM, which fixes the query and submits again)
         |
   7e. LLM writes the final response_text from the submitted result
         |
         v
8. Save QueryHistory to App DB
         |
         v
9. Save ConversationMessage (user + assistant) if conversation_id provided
         |
         v
10. Return { success, generated_sql, columns, rows, response_text, connection_name }
```

### User Registration + Onboarding Flow

```
POST /api/auth/register         create User (Argon2 hash password)
POST /api/auth/login            get JWT token
GET  /api/auth/onboarding-status { has_connection: false, has_knowledge_base: false }
  -> Frontend shows OnboardingPage
POST /api/connections           create DBConnection (Fernet-encrypted password)
POST /api/knowledge/{id}/group  create KnowledgeBase with selected tables
GET  /api/auth/onboarding-status { onboarding_complete: true }
  -> Frontend shows main app (ChatPage)
```

---

## 10. Security Architecture

| Layer | Implementation |
|---|---|
| Authentication | JWT Bearer tokens (HS256), 24h expiry |
| Password storage | Argon2 (via passlib) — one-way hash |
| DB credential storage | Fernet symmetric encryption — reversible (needed for connection) |
| SQL injection prevention | sql_guard.sanitize_table_name() + SafeSqlExecutor AST validation (sqlglot) + EXPLAIN validation |
| Data mutation prevention | Multi-layer defense: AST tree check blocks all DML/DDL/locking nodes & functions; DB transaction enforcement via SET TRANSACTION READ ONLY; execution bounded by statement_timeout |
| Rate limiting | Sliding window on both IP and user ID |
| CORS | Configured in main.py; currently allows wildcard — tighten for production |

---

## 11. Caching Strategy

| Cache Key Pattern | Data | TTL | Invalidation |
|---|---|---|---|
| `tables:{url_md5}` | Table name list | 1h | TTL only |
| `schema:{url+tables_md5}` | Schema context string | 1h | TTL only |
| `table_schema:user:{u}:connection:{c}:table:{t}` | Column details | 1h | TTL only |
| `preview:user:{u}:connection:{c}:table:{t}` | Table preview rows | 1h | TTL only |
| `kb:user:{u}:connections:all` | All KB groups | No TTL | On KB create/delete |
| `kb:user:{u}:connection:{c}:groups` | KB groups for conn | No TTL | On KB create/delete |
| `initial_suggestions:user:{u}:connection:{c}:kb:{k}` | Suggestions | 1h | force_refresh param |
| `rate_limit:chat:ip:{ip}` | Request timestamps | window + 10s | Sliding removal |
| `rate_limit:chat:user:{u}` | Request timestamps | window + 10s | Sliding removal |

---

## 12. Rate Limiting

**Algorithm:** Redis sorted sets — each request adds a member with `{timestamp: score=timestamp}`. Old members outside the window are pruned before counting.

**Current limits:** 3 requests per 90 seconds per IP AND per user (both must pass).

**Endpoints affected:** `POST /api/query/chat` only.

**To add rate limiting to another endpoint:** Call `check_rate_limit(user_id, client_ip)` at the top of the handler.

---

## 13. Dependency Map

```
main.py
+-- app.database               <- config.py
+-- app.routers.auth           <- models.user, utils.security
+-- app.routers.connections    <- models.connection, utils.security, utils.db_manager
+-- app.routers.schema         <- models.connection, utils.db_manager, services.redis_client
+-- app.routers.knowledge      <- models.knowledge, utils.security, services.redis_client
+-- app.routers.query          <- models.*, utils.security, utils.db_manager,
|                                 services.sql_agent, services.rate_limiter
+-- app.routers.history        <- models.query_history, utils.security
+-- app.routers.conversations  <- models.conversation, utils.security
+-- app.routers.suggestions    <- models.*, utils.db_manager, services.redis_client, utils.prompts
+-- app.services.sql_agent     <- services.validate_sql (SafeSqlExecutor)
+-- app.services.validate_sql  <- utils.db_manager (refine_sql_from_markdown), sqlglot
```

---

## 14. Where to Change Things

| Goal | File(s) to Edit |
|---|---|
| Change JWT expiry | `config.py` - ACCESS_TOKEN_EXPIRE_MINUTES |
| Change LLM model (Gemini version) | `services/sql_agent.py` - model= in generate_response() AND `services/suggestions.py` - model= in both endpoints |
| Change system prompt for SQL agent | `services/sql_agent.py` - generate_system_prompt() |
| Change suggestion prompt templates | `utils/prompts.py` - initial_suggestions_prompt / conversation_suggestions_prompt lambdas |
| Add a new API endpoint | Create/edit the relevant router file in `routers/`, add app.include_router() in main.py |
| Add a new database table | Create file in `models/`, add import to `database.py::init_db()` |
| Change rate limit thresholds | `services/rate_limiter.py` - RATE_LIMIT_MAX_REQUESTS / RATE_LIMIT_WINDOW_SECS |
| Add a new allowed SQL query type | `services/validate_sql.py` - `_ALLOWED_ROOTS` or `_FORBIDDEN_NODES` in SafeSqlExecutor |
| Change forbidden SQL functions or prefixes | `services/validate_sql.py` - `_FORBIDDEN_FUNCTIONS` or `_FORBIDDEN_FUNCTION_PREFIXES` |
| Change query execution timeout or row limit | `services/validate_sql.py` - SafeSqlExecutor timeout_ms / max_rows, OR `services/sql_agent.py` create_sql_tool() |
| Add support for non-PostgreSQL DBs | `utils/db_manager.py` - get_user_db_url() (change postgresql:// prefix), `models/connection.py` (add db_type field) |
| Change Redis TTL for caching | Edit the ex= parameter in the relevant redis_client.set() call |
| Change which tables LLM sees | `routers/query.py` - chat_query() table filtering logic |
| Change CORS origins | `main.py` - allow_origins=[...] |
| Disable rate limiting | Remove check_rate_limit() call from routers/query.py::chat_query() |
| Add a new tool to the SQL agent | Define with @tool in services/sql_agent.py, add to build_workflow() ToolNode and llm.bind_tools([...]) |
| Change schema display format for LLM | `utils/db_manager.py` - get_schema_context() function |
| Modify markdown SQL cleanup logic | `utils/db_manager.py` - refine_sql_from_markdown() function |
| Change number of preview rows | `routers/schema.py` - LIMIT clause in preview_table() |
| Change max rows stored in conversation | `routers/query.py` - rows[:50] slice in chat_query() |
