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
    |   ├── query.py             # POST /chat (NL to SQL), POST /{id}/execute-sql
    |   ├── history.py           # GET query history
    |   ├── conversations.py     # CRUD for chat conversations
    |   └── suggestions.py       # AI-generated query suggestions
    |
    ├── services/                # Business logic / AI integrations
    |   ├── __init__.py
    |   ├── sql_agent.py         # LangGraph + Gemini SQL agent (core AI loop)
    |   ├── validate_sql.py      # SQL safety validation + schema EXPLAIN + execution
    |   ├── rate_limiter.py      # Sliding-window rate limiter (Redis sorted sets)
    |   └── redis_client.py      # Redis wrapper (get/set/delete with JSON auto-encode)
    |
    └── utils/                   # Cross-cutting helpers
        ├── __init__.py
        ├── security.py          # JWT, Argon2, Fernet encryption, get_current_user
        ├── db_manager.py        # SQLAlchemy engine cache for user DBs, test_connection
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

### `app/database.py`

```python
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():   # FastAPI dependency - yields a session, closes it after
def init_db():  # Called on startup - creates all tables via Base.metadata.create_all()
```

- **App DB** is a single PostgreSQL instance configured via `DATABASE_URL`.
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
| `connection_id` | Integer FK to db_connections | |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC, auto-updated |

### `app/models/query_history.py` — `QueryHistory`

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `user_id` | Integer FK to users | |
| `connection_id` | Integer FK to db_connections | |
| `nl_query` | Text | Original natural language question |
| `generated_sql` | Text | SQL generated by agent |
| `success` | Boolean | Did the query execute successfully? |
| `error_message` | Text | Error if success=False |
| `created_at` | DateTime | UTC |

### `app/models/conversation.py` — `Conversation` + `ConversationMessage`

**`Conversation`**

| Column | Type | Notes |
|---|---|---|
| `id` | String PK | UUID provided by frontend |
| `user_id` | Integer FK to users | |
| `name` | String | Display title |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC, auto-updated |

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
| POST | `/guest-login` (or `/guest`) | No | Instant guest login. Preloads shop DB connection, knowledge base, and mock conversations. Returns JWT access_token. |
| GET | `/me` | JWT | Returns current user info (including `is_guest: boolean`). |
| GET | `/onboarding-status` | JWT | Returns has_connection, has_knowledge_base, onboarding_complete. Used by frontend router. |

### `app/routers/connections.py` — prefix `/api/connections`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/` | JWT | Create new DB connection. Tests connection first. Encrypts password with Fernet. |
| GET | `/` | JWT | List all connections for current user. |
| POST | `/test` | JWT | Test a connection without saving. |
| DELETE | `/{conn_id}` | JWT | Delete connection. Also removes cached engine via `remove_engine()`. |

**To add a new connection field:** Update `DBConnection` model, `ConnectionCreate`, and `ConnectionResponse` schemas in `connections.py`.

### `app/routers/schema.py` — prefix `/api/schema`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/{conn_id}/tables` | JWT | Lists all tables with column counts. No cache. |
| GET | `/{conn_id}/tables/{table_name}/columns` | JWT | Column info + PK + FK. Redis cached. |
| GET | `/{conn_id}/tables/{table_name}/preview` | JWT | First 10 rows of a table. Redis cached. |

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
| POST | `/{conn_id}/execute-sql` | JWT | Execute a raw SQL string provided by user (from View Code / edit mode). Validates and runs via execute_raw_sql. Saves to history. |

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

### `app/services/guest_service.py` — Guest Workspace Provisioner

Provisions isolated guest accounts on demand when users click "Login as Guest":
- Creates unique `User` (`guest_{uid}@sqlnav.demo`).
- Preloads `DBConnection` targeting the PostgreSQL `shop` database (customizable via `GUEST_DB_*` settings).
- Preloads `KnowledgeBase` named `"Shop Catalog & Orders"` with all 9 e-commerce tables.
- Seeds 3 rich mock conversations with SQL queries, product result cards (including real FakeStoreAPI images), aggregation metrics, and markdown analysis.
- Populates `QueryHistory` with initial historical queries.

### `app/services/sql_agent.py` — The Core AI System

**Class: `SQLAgent`**

Implements a LangGraph ReAct-style agentic loop:

```
User Question
     |
     v
generate_response (Gemini 2.5 Flash with schema in system prompt)
     |
     +-- tool_call? YES --> execute_sql_query tool
     |                           |
     |                     ValidateSqlQuery.validate()
     |                     is_safe + schema_validated?
     |                     Execute via SQLAlchemy
     |                     Returns rows/columns
     |
     |<---- Tool result fed back to LLM
     |
     +-- tool_call? NO --> Final response text
     |
     v
Return { success, generated_sql, columns, rows, response_text }
```

**Key internals:**

- `SQLAgent.__init__(engine, schema_context)` — builds system prompt with DB schema.
- `generate_system_prompt(schema_context)` — embeds full schema into the LLM system message.
- `build_workflow()` — creates LangGraph `StateGraph` with generate_response → tools → conditional edges. Uses `SqliteSaver` checkpointer with `checkpoints.sqlite` for multi-turn memory.
- `run_query(user_input, conversation_id)` — invokes the graph with `thread_id=conversation_id` to maintain per-conversation context.
- `execute_sql_query` tool (created by `create_sql_tool`) — validates SQL via `ValidateSqlQuery` then executes.

**To change the LLM model:** Change `model="gemini-2.5-flash"` in `generate_response()`.

**To change the system prompt:** Edit `generate_system_prompt()`.

**To add a new tool:** Define with `@tool` decorator, add to `build_workflow()` ToolNode and `llm.bind_tools()`.

---

### `app/services/validate_sql.py`

**Class: `ValidateSqlQuery`**

Two-phase SQL safety system before any execution:

**Phase 1 — `_is_query_safe(sql)`** (regex + sqlparse structural check):
- Allows only `SELECT` / `UNKNOWN` (CTEs) statement types.
- Blocklist keywords: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `REPLACE`, `MERGE`, `GRANT`, `REVOKE`, `EXEC`, `EXECUTE`, `CALL`, `INTO`.
- Checks for `SELECT INTO` pattern separately.
- Checks comments for dangerous keywords.

**Phase 2 — `_validate_against_schema(sql)`**:
- Runs `EXPLAIN {sql}` against the actual DB to validate table/column references without executing.

**Phase 3 — `_execute_sql_query(sql)`**:
- Executes validated query, returns `{ success, columns, rows }`.

**Standalone helper functions:**

| Function | Description |
|---|---|
| `refine_sql_from_markdown(text)` | Strips markdown code fences, normalizes whitespace, ensures trailing semicolon |
| `get_all_table_names(engine)` | Returns table names from DB, Redis cached (1h) using URL MD5 hash |
| `get_schema_context(engine, table_names)` | Builds human-readable schema string with column types, PK/FK info. Redis cached (1h) using URL+tables MD5 hash |
| `execute_raw_sql(engine, sql)` | Validates then executes user-provided SQL (used by execute-sql endpoint) |

**To change what queries are allowed:** Modify `_is_query_safe()` dangerous_keywords list or `allowed_types` list.

**To change schema representation for the LLM:** Modify `get_schema_context()` — it builds the string fed into the agent's system prompt.

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
| `test_connection(host, port, db_name, username, password)` | Test DB connectivity (runs SELECT 1). Returns { success, message }. |
| `remove_engine(conn_id)` | Disposes and removes cached engine for a connection (called on delete). |

The engine cache (`_engine_cache`) prevents creating new connection pools on every request.

---

### `app/utils/prompts.py`

Two lambda prompt templates:

- `initial_suggestions_prompt(schema_context)` — asks LLM for 4 varied questions about the DB.
- `conversation_suggestions_prompt(schema_context, history_text)` — asks LLM for 3 follow-up questions based on recent conversation.

**To change suggestion prompts:** Edit these lambda functions directly.

---

### `app/utils/sql_guard.py`

- `validate_sql(sql)` — blocklist check + SELECT-only enforcement + auto-adds `LIMIT 1000`. Simpler guard than `ValidateSqlQuery`.
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
5. get_all_table_names(engine)                  [validate_sql.py - Redis cached]
         |
         v
6. get_schema_context(engine, context_tables)   [validate_sql.py - Redis cached]
         |
         v
7. SQLAgent(engine, schema_context).run_query() [sql_agent.py]
         |
   7a. LangGraph invokes generate_response node (Gemini with schema in system prompt)
         |
   7b. Gemini decides to call execute_sql_query tool with generated SQL
         |
   7c. ValidateSqlQuery.validate_sql_query(sql)
         |    - _is_query_safe() - regex checks
         |    - _validate_against_schema() - EXPLAIN validation
         |
   7d. ValidateSqlQuery._execute_sql_query(sql)
         |    - SQLAlchemy execute - returns columns, rows
         |
   7e. Tool result fed back to Gemini
         |
   7f. Gemini generates final response_text (natural language summary)
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
| SQL injection prevention | sql_guard.sanitize_table_name() + ValidateSqlQuery blocklist + EXPLAIN validation |
| Data mutation prevention | Only SELECT queries allowed; _is_query_safe() blocks all DML/DDL |
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
|                                 services.sql_agent, services.validate_sql, services.rate_limiter
+-- app.routers.history        <- models.query_history, utils.security
+-- app.routers.conversations  <- models.conversation, utils.security
+-- app.routers.suggestions    <- models.*, utils.db_manager, services.validate_sql,
                                  services.redis_client, utils.prompts
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
| Add a new allowed SQL query type | `services/validate_sql.py` - allowed_types list in _is_query_safe() |
| Add support for non-PostgreSQL DBs | `utils/db_manager.py` - get_user_db_url() (change postgresql:// prefix), `models/connection.py` (add db_type field) |
| Change Redis TTL for caching | Edit the ex= parameter in the relevant redis_client.set() call |
| Change which tables LLM sees | `routers/query.py` - chat_query() table filtering logic |
| Change CORS origins | `main.py` - allow_origins=[...] |
| Disable rate limiting | Remove check_rate_limit() call from routers/query.py::chat_query() |
| Add a new tool to the SQL agent | Define with @tool in services/sql_agent.py, add to build_workflow() ToolNode and llm.bind_tools([...]) |
| Change schema display format for LLM | `services/validate_sql.py` - get_schema_context() function |
| Change number of preview rows | `routers/schema.py` - LIMIT clause in preview_table() |
| Change max rows stored in conversation | `routers/query.py` - rows[:50] slice in chat_query() |
