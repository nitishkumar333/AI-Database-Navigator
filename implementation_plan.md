# Plan: from a single-shot NL→SQL demo to a production agent

**Structural limits in the code:**
- query.py puts every table's schema into the system prompt. That breaks past roughly 100–200 tables.
- get_schema_context emits only names, types, PKs and FKs. There are no descriptions, sample values, row counts or comments.
- `execute_sql_query` is the agent's only tool, and the prompt says to run "one query".
- route_after_tools ends an eval run on the **first successful** query. Once the agent can run exploratory queries, the eval would score a probe like `SELECT DISTINCT segment …` as the answer. This has to change along with the agent.
- Self-correction only happens on SQL *errors*. A query that runs but returns wrong, empty or inflated results is accepted.
- The endpoint is synchronous, rebuilds `SQLAgent` (and calls `bind_tools`) on every request, and trims history by message count rather than tokens.

---

## 1. Your design questions

**"Can't pass all schemas, but the LLM needs schema context."** Correct. Use **tiered schema context**, not "all or nothing":
- **Tier 1, always in the prompt:** a compact catalog with each table's name, a one-line description and its row count. That's about 15–25 tokens per table, so 300 tables is roughly 6k tokens.
- **Tier 2, on demand:** full column details, sample values and join paths, fetched through a tool for the tables the agent picks.
- **Tier 3, retrieval:** only needed when even the catalog is too big (500+ tables) or for matching literal values.
- **Small databases:** if the whole enriched schema fits in about 8k tokens, just include it. Retrieval adds error modes (missing a table), so use it only when you have to.

**Parallel queries.** Yes, for *exploration*: distinct values, counts, checking a join's cardinality. LangGraph's `ToolNode` already runs parallel tool calls concurrently when the model emits several in one turn. You need to:
- Allow it in the prompt.
- Add a semaphore, because the engine pool is `pool_size=2, max_overflow=3`.
- Set a per-turn query budget.

The final answer should still be one deliberate query.

**Reformulating when results are bad.** Yes. This is the biggest behavioural gap. Add a **verifier** that checks results, not just errors (Phase 4).

**More agentic?** Yes, but **bounded**. A free-form ReAct loop with mid-tier models wanders and burns tokens. Use a structured graph instead: route → link schema → explore and draft → verify → answer, with explicit budgets and a fast path for simple questions.

**Vector DB, graph DB, or hybrid?**
- **Graph DB (Neo4j etc.): not worth it.** A foreign-key graph is a few thousand edges at most. Hold it in memory with `networkx`, cached per connection, and use it to compute join paths. A separate database adds ops cost for no benefit.
- **Vector search: worth it, inside the Postgres you already run.** Use **pgvector** plus **pg_trgm**, not a separate vector DB. You already have Postgres for the checkpointer. `chromadb` is in requirements, but it's another stateful service to operate.
- **Use hybrid retrieval.** Database identifiers and values match better lexically (`cust_seg` ↔ "segment", `'CZK'` ↔ "czech"). Combine trigram/BM25 with embeddings and merge the rankings with reciprocal rank fusion.
- **What to index**, in order of value:
  1. Column documents: name, type, description and sample values.
  2. Distinct values of low-cardinality text columns, for value linking.

---

## 2. Target architecture

```
                   ┌────────────────────────────────────────────┐
 OFFLINE (per      │ Schema Profiler → Describer (LLM) → Indexer │
 connection, on    │  pg_catalog, pg_stats, comments, FK infer   │──► app Postgres
 connect + diff)   └────────────────────────────────────────────┘    (catalog tables,
                                                                      pgvector, trgm)
 ONLINE (per turn)
 question
   │
   ▼
 [1 Router] ── chit-chat / needs-clarification ──► reply / interrupt()
   │ standalone question (follow-ups rewritten using history)
   ▼
 [2 Schema Linker]  hybrid retrieval → candidate tables/cols/values
   │                + FK-graph expansion (bridge tables)
   ▼
 [3 Agent loop]  tools: search_schema · describe_tables · find_values
   │             · run_sql (exploratory, parallel) · submit_answer
   │             budget: ≤ N tool calls, ≤ M SQL runs, token cap
   ▼
 [4 Verifier]  deterministic checks + LLM critic ── fail (≤2x) ──► back to 3
   │ pass
   ▼
 [5 Answer]  stream answer + SQL + assumptions made
```

Simple questions take the path 1 → 2 → 3 (a single `submit_answer`) → 4 (deterministic checks only) → 5, which keeps latency close to today's.

---

## 3. Phased implementation (ordered by accuracy gain per unit of effort)

### Phase 0: Trustworthy evaluation (1–2 days). Do this first.
- Add a **schema-linking recall** metric: parse `gold_sql` with sqlglot (already a dependency), extract its tables and columns, and check they appear among the tables the agent retrieved or described. This tells you whether a failure came from retrieval or from SQL generation.
- Log tool calls per question, verifier rejections and cost per difficulty level.

### Phase 1: Schema profiling and an enriched schema (biggest cheap win)
New module `backend/app/services/schema_index/`:
- **`profiler.py`**: reads only catalogs and statistics, with no table scans:
  - `pg_class.reltuples` for row counts.
  - `pg_description` for existing comments.
  - **`pg_stats`** for `null_frac`, `n_distinct`, `most_common_vals` and `histogram_bounds`. Postgres already maintains these, so you get sample values without scanning.
  - Format detection on text columns, for example "TEXT shaped like YYYYMM" or "numeric stored as text".
- **Infer missing foreign keys.** Many real databases (and BIRD) don't declare them. Match column names (`customerid` ↔ `customers.customerid`), then confirm with a value-containment check on a `TABLESAMPLE`.
- **`describer.py`**: one LLM call per table, batched, to produce a table description and per-column descriptions from the profile. Store them and **make them editable in the UI**, because human edits beat generated text.
- **New models** in `backend/app/models/`: `SchemaTable`, `SchemaColumn` (description, profile JSON, sample values, embedding), `SchemaRelation` (declared or inferred, with confidence), and a `schema_hash` per connection.
- **Refresh:** hash `information_schema.columns` and re-profile only changed tables. Run it as a background job; you already have Redis, so `arq` or RQ is lightweight (will do this later).
- **Prompt rules for SQL dialect pitfalls:** cast `REAL` to `double precision` before aggregating, use `NULLIF` for divisors, and handle text-encoded dates using the detected format.
- Rewrite `get_schema_context` to emit a compact enriched format, for example:
  `yearmonth.date TEXT -- year+month 'YYYYMM', e.g. '201301','201302'`

### Phase 2: Tool redesign and the agent loop
Replace the single tool in [sql_agent.py](backend/app/services/sql_agent.py) with these:

| Tool | Purpose |
|---|---|
| `search_schema(query)` | Hybrid search over tables and columns; returns short descriptions |
| `describe_tables(tables[])` | Columns, types, descriptions, samples, PK/FK, and **join paths between the given tables** (computed on the FK graph) |
| `find_values(text, column?)` | Value linking ("czech" → `currency='CZK'`) using the trigram index, falling back to a live `ILIKE … LIMIT 10` |
| `run_sql(sql, purpose)` | Exploratory; returns at most 20 rows plus row count; parallel-safe |
| `submit_answer(sql, assumptions)` | Final query; executed with the full row limit; **ends the loop** |

- Eval mode then ends on `submit_answer` instead of the first successful tool. This fixes the termination bug above.
- Update the prompt:
  - Explore first when unsure.
  - Do arithmetic in SQL, never in the model's head.
  - Batch independent checks into one turn as parallel tool calls.
- **Budgets:** about 8 tool calls and 6 SQL runs per turn, enforced in graph state rather than via `recursion_limit`. When the budget runs out, force a `submit_answer` with the best query so far.
- Compile the graph **once per process**. Pass connection-specific tools and context through `config["configurable"]`, not by rebuilding `SQLAgent` on every request.

### Phase 3: Retrieval for large schemas
- Run `CREATE EXTENSION vector, pg_trgm` in the app database.
- Embed the column and table documents with any embedding model, behind a small `embeddings.py` factory like your [llm_factory.py](backend/app/services/llm_factory.py).
- **Schema linker node** (runs before the agent):
  1. Hybrid top-k columns, then group them by table.
  2. Expand to a connected subgraph using shortest paths or an approximate Steiner tree over the FK graph, so bridge tables get included.
  3. Inject the result as Tier-2 context so the agent rarely has to call `describe_tables` on simple questions.
- Your existing `KnowledgeBase.tables` filter becomes a scope restriction applied on top of retrieval.
- **Trigger:** use retrieval only when the enriched schema exceeds the token threshold; otherwise include the full schema.

### Phase 4: Verifier and result-aware self-correction
Add a node after `submit_answer`:
- **Deterministic checks (free):**
  - Empty result → probe the filter values with `find_values`.
  - All NULL.
  - **Join fan-out:** compare `COUNT(*)` with `COUNT(DISTINCT pk)` on the driving table.
  - The question says "which one" or "top N" but there's no `LIMIT`/`ORDER BY`, or the reverse.
  - Selected columns don't match what the question asks for.
  - The magnitude is implausible compared with column statistics from `pg_stats`.
- **LLM critic** (complex route only): sees the question, SQL, a result sample and the assumptions. It returns pass, or fail with a specific fix. Allow at most two revisions.

### Phase 5: Production hardening
- **Async and streaming:**
  - Make the endpoint `async def` with `graph.astream_events`.
  - Stream step events ("Searching schema…", "Running 3 checks…", "Verifying…") to the frontend through your socket context.
  - Use async engines, or `run_in_executor` for SQL.
- **Context management:**
  - Trim by tokens, not message count.
  - Summarise tool outputs before replaying them: row count, column statistics and the first k rows.
  - Store `last_sql` and `last_tables` in graph state so follow-ups ("now split by year") don't re-retrieve.
  - Summarise turns older than N.
- **Query safety** (your `SafeSqlExecutor` is already solid):
  - Parse the `EXPLAIN (FORMAT JSON)` total cost you already compute and reject queries over a threshold.
  - Add `SET LOCAL work_mem`.
  - Recommend a per-connection SELECT-only role during onboarding.
  - Merge [sql_guard.py](backend/app/utils/sql_guard.py)'s regex checks into the AST validator so there's one source of truth.
- **Prompt injection from data:** row values go into the LLM's context, so treat tool output as data in the system prompt. The agent has no write tools, which limits the damage. Add an option to mask PII columns flagged during profiling.
- **Reliability:**
  - Retry LLM calls with tenacity (already a dependency), with a fallback provider.
  - Set a wall-clock timeout for the whole turn.
  - When budgets run out, return a partial answer with an explanation instead of an error.
- **Caching:** per-connection normalized question → SQL that passed the verifier, invalidated when the schema hash changes. Keep the existing Redis schema caches.
- **Observability:**
  - Enable LangSmith (already installed), or OpenTelemetry (also installed).
  - Persist an `AgentRun` row per turn: tool calls, tokens, latency, verifier verdicts.
  - Your `_collect_trace` is a good starting point.
- **Cost controls:** per-user token budgets alongside the existing rate limiter. Use a cheap model for routing, descriptions and the critic, and a strong model for the agent loop.

---

## 4. Suggested code layout

```
backend/app/services/
  agent/
    graph.py          # build + compile once; node wiring, budgets
    state.py          # AgentState: messages, standalone_q, candidates, budget, last_sql, verdicts
    tools.py          # search_schema, describe_tables, find_values, run_sql, submit_answer
    nodes/router.py, schema_linker.py, verifier.py, answer.py
    prompts.py
  schema_index/
    profiler.py  describer.py  indexer.py  retriever.py  join_graph.py  refresh.py
  embeddings.py
backend/app/models/
  schema_catalog.py   # SchemaTable, SchemaColumn, SchemaRelation
  agent_run.py
```

Keep the `SQLAgent.run_query` signature as a thin wrapper so [query.py](backend/app/routers/query.py) and [evaluation/runner.py](evaluation/runner.py) keep working while the internals change.

---

## 5. What to expect

Rough expectations from BIRD-style systems:
- Phases 1 and 2 (enriched schema plus exploration) usually give the largest gain on moderate and challenging questions.
- Phase 3 is mainly about **scaling** (staying accurate as table count grows), not raw accuracy on small databases.
- Phase 4 trades latency and cost for accuracy, so keep it on the complex route only.