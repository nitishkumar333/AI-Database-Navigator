# SQL Agent Evaluation

Tests how well the SQL agent writes SQL. It asks the agent questions from the
Arcwise-Plat dataset (498 questions on the 11 BIRD databases), runs the agent's
SQL and the correct ("gold") SQL, and checks whether both return the same rows.

Only the SQL is tested, not the final text answer. The agent stops as soon as
its query works, so no tokens are spent on writing an answer.

## Dataset

[`data/arcwise_plat_postgresql.csv`](data/arcwise_plat_postgresql.csv) has the
same columns as BIRD (`question_id, db_id, question, evidence, SQL, difficulty`).

- **Source.** Arcwise-Plat ("full" variant) from Jin et al., *Pervasive Annotation
  Errors Break Text-to-SQL Benchmarks and Leaderboards* (arXiv 2601.08778;
  <https://github.com/uiuc-kang-lab/text_to_sql_benchmarks>).
  - It is BIRD Mini-Dev with corrected gold SQL, questions and evidence. The
    authors found annotation errors in 52.8% of the original Mini-Dev examples.
  - BIRD is licensed CC BY-SA 4.0.
  - q119 and q120 are dropped, as in Arcwise-Plat.
  - Arcwise-Plat has no difficulty labels, so `difficulty` is copied from BIRD
    Mini-Dev (the July 2025 release) by `question_id`.
- **Ported from SQLite to PostgreSQL, and every query verified.** Each gold
  query was run as published on the BIRD SQLite databases (`minidev_0703`
  package), then run ported on the Postgres `bird` database, and the outputs
  were compared: same rows, duplicates counted, order ignored.
  - 477 of 498 outputs are identical.
  - The other 21 differ only beyond the 6th significant digit, because Postgres
    stores those columns as `real` (float4) while SQLite uses 8-byte doubles.
  - 484 queries converted automatically and 14 were ported by hand. The
    conversion keeps SQLite semantics:
    - `CAST(... AS REAL)` becomes `DOUBLE PRECISION`;
    - `real` columns are summed and averaged as `double precision`;
    - `SUM(condition)` becomes `SUM(CASE WHEN ...)`;
    - `LIKE` on date columns casts them to text;
    - text columns compared with numbers compare as text;
    - `SUBSTR(x, -n)` becomes `RIGHT(x, n)`;
    - loose `GROUP BY` lists are completed;
    - `date(x, '+N years')` becomes `x + INTERVAL 'N years'`.
- **Sessions run in UTC+8.** The Postgres `bird` dump stores the
  `codebase_community` timestamps as `timestamptz` shifted by −8 hours from the
  original values. `create_bird_engine` therefore sets `timezone=Asia/Shanghai`,
  so the times in questions (for example "20:29:39 on 2014/4/23") mean the same
  thing as in the data. Any other client of the `bird` database needs the same
  setting, or `ALTER DATABASE bird SET timezone = 'Asia/Shanghai'`.
- **12 answers depend on today's date.** Questions about ages or "now"
  (q194, q898, q1031, q1156, q1227, q1229, q1232, q1235, q1239, q1242, q1243,
  q1257) use `CURRENT_DATE` or `CURRENT_TIMESTAMP`. Gold and predicted SQL run
  at the same moment, so scoring stays consistent, but these gold outputs change
  over time.

## Setup (once)

1. Start Postgres: `docker compose up -d postgres` (the `bird` database must exist).
2. Install packages: `backend/venv/Scripts/pip install -r backend/requirements.txt`
3. Copy `evaluation/.env.example` to `evaluation/.env` and fill in an API key
   (`GEMINI_API_KEY` or `GROQ_API_KEY`).
4. Check that the dataset and database are OK. This uses no API calls:

   ```bash
   backend/venv/Scripts/python -m evaluation check-gold --split dev150
   ```

## Run

Run all commands from the repo root.

```bash
# the frozen 30-question smoke set (cheap; use while iterating)
backend/venv/Scripts/python -m evaluation run --provider groq --split smoke30 --run-name my-test

# the frozen 150-question benchmark (use before merging a change)
backend/venv/Scripts/python -m evaluation run --provider groq --split dev150 --rpm 20 --run-name my-change-dev150

# all 498 questions with Groq, max 10 requests per minute
backend/venv/Scripts/python -m evaluation run --provider groq --rpm 10 --run-name groq-full

# re-score a finished run without calling the LLM
backend/venv/Scripts/python -m evaluation score --run-name my-test

# compare runs on the questions they share (first = baseline), no LLM calls
backend/venv/Scripts/python -m evaluation compare baseline-dev150 my-change-dev150 --out my-change.md
```

- **Stopped halfway?** Run the same command again with the same `--run-name`.
  It skips questions that are already done. Add `--fresh` to start over.
- **Out of quota?** The run stops on its own. Run it again later with the same `--run-name`.

Other useful options:

| Option | What it does |
|---|---|
| `--split NAME` | a frozen question set from `data/splits/` (`smoke30`, `dev150`) |
| `--limit N` | only the first N questions |
| `--sample N` | a random stratified sample (changes with `--seed`; prefer `--split` for comparisons) |
| `--db-id X`, `--difficulty simple`, `--question-id 5` | pick specific questions |
| `--model X` | use a different model |
| `--no-evidence` | don't give the agent the dataset's hint text (closer to real users) |
| `--schema-format basic` | the schema format from before profiling, to measure what profiling adds (default `enriched`) |
| `--describe` | add LLM-written table/column descriptions, as production does. One LLM call per table, cached per model in `evaluation/.cache/descriptions/`, so each table is described once across runs |
| `--output-rows N` | result rows saved per question (default 100, 0 = all) |

## Results

Results are saved in `evaluation/results/<run-name>/`:

| File | What's in it |
|---|---|
| `report.md` | **Start here.** The summary of scores. |
| `failures.jsonl` | Every question the agent got wrong, one per line. Use it to see what went wrong. |
| `predictions.jsonl` | Every question, right or wrong. |
| `summary.json` | Same numbers as `report.md`, as JSON. |
| `config.json` | Model and options used for the run. |

### What the report means

**Accuracy scores** (higher is better, shown per difficulty and per database):

| Score | Meaning |
|---|---|
| **EX** | The main score: % of questions where the agent's rows exactly match the gold rows. Row order doesn't matter, but the columns must match. |
| **EX (column-tolerant)** | Same, but extra columns are allowed. If this is much higher than EX, the agent often returns extra columns. |
| **Soft-F1** | Partial credit: how many of the right rows and values the agent got, even if not all. |

**Outcome breakdown**: what happened to each question.

| Status | Meaning |
|---|---|
| `correct` | Right answer. |
| `wrong_result` | The SQL ran but returned different rows. |
| `no_sql` | The agent never wrote a query that worked. |
| `pred_error` / `pred_timeout` | The agent's SQL failed or was too slow when re-run. |
| `agent_error` | The LLM or agent crashed. |
| `gold_error` | The correct SQL itself failed. Not counted in the scores. |

**Cost & behaviour**: tokens used, LLM calls per question, response time
(p50 = typical, p95 = slowest 5%), and how often the agent fixed its own SQL
after an error.

### One question in `failures.jsonl` / `predictions.jsonl`

| Field | Meaning |
|---|---|
| `question`, `evidence` | What was asked, and the hint given |
| `gold_sql`, `pred_sql` | Correct SQL and the agent's SQL |
| `gold_sql_output`, `pred_sql_output` | Rows each query returned |
| `attempted_sql`, `tool_errors` | Every query the agent tried, and the errors it got |
| `status`, `metrics` | Outcome and scores for this question |
| `tool_calls`, `llm_calls`, `usage` | Tool calls by name, LLM calls and tokens for this question |
| `context_tables` | Tables whose schema the agent had available |
| `linking` | Tables/columns the gold and predicted SQL use, and the recall/precision between them |
| `failure_category` | Why it was missed (see below); empty when correct |

### Newer report sections

- **EX 95% CI**: the range the true accuracy probably lies in. At 30 questions it
  is about ±17 points, and at 150 questions about ±8. Two runs whose ranges
  overlap a lot are not reliably different.
- **Why questions were missed**: one heuristic cause per missed question,
  checked in this order:

  | Category | Meaning | What usually fixes it |
  |---|---|---|
  | `extra_columns` | Right rows, plus extra columns | Prompt rules on what to SELECT |
  | `wrong_tables` | Used different tables than gold | Schema descriptions, retrieval (schema linking) |
  | `wrong_columns` | Same tables, missed a column gold uses | Column descriptions, sample values |
  | `wrong_projection` | Different number of output columns | Prompt rules on output shape |
  | `wrong_row_count` | Same shape, different row count | Filter values, join fan-out, LIMIT logic |
  | `wrong_values` | Same shape and row count, different values | Business definitions (glossary), type casts |
  | `no_sql`, `pred_error`, ... | See the status table above | |

- **Schema linking**: compares the tables and columns used by the predicted SQL
  with those used by the gold SQL. Aliases (`T1`, `T2`) and unqualified columns
  are resolved against the real schema with sqlglot.
  - *Gold tables present in agent context* is always 100% for now, because the
    agent gets the whole per-database schema. It becomes the main retrieval
    metric once the agent retrieves schema itself (an agent can report what it
    looked at as `trace["context_tables"]`).
  - *EX when table set is exact/wrong* shows how much accuracy is lost to
    picking the wrong tables versus writing the wrong SQL on the right tables.
- **Cost & behaviour by difficulty**: tokens, LLM calls, tool calls and latency
  per difficulty level.

Old runs can get these sections without any LLM calls: `python -m evaluation score --run-name <run>`.

## Frozen splits

`data/splits/` holds committed question sets, stratified by database and
difficulty. They never change, so runs made weeks apart are scored on exactly
the same questions.

| Split | Questions | Use it for |
|---|---:|---|
| `smoke30` | 30 (a subset of `dev150`) | Quick checks while changing the agent |
| `dev150` | 150 | Deciding whether a change goes in |

Create a new one with
`python -m evaluation make-split --name NAME --size N [--from-split dev150]`.
Existing splits are never overwritten unless you pass `--force`. Don't do that
for a split you already have results on.

## Comparing runs

`python -m evaluation compare BASELINE RUN [RUN ...]` scores every run on the
questions they all share, then for each run shows:

- every metric side by side;
- **fixed / broken** questions relative to the baseline, with their ids;
- an exact **McNemar p-value**. This paired test asks whether the fixed vs broken
  split could be chance. It needs far fewer questions than comparing two
  accuracy numbers;
- how the failure categories changed.

**Rule for agent changes:** run `dev150` with the change, then compare it
against the current baseline on `dev150`. Merge only if the net change is
positive and nothing important broke. Use the fixed and broken ids to read
those questions in `predictions.jsonl`.

## Saving quota

Each question currently costs about one LLM call and roughly 1k tokens, so
`smoke30` ≈ 30k tokens and `dev150` ≈ 150k tokens. Agentic versions will cost
several times more per question, so check your provider's daily limits first.

- Iterate on `smoke30`. Run `dev150` only once per finished change.
- Use `--rpm` to stay under per-minute limits. A run that hits a daily limit
  stops; re-run the same command later to continue.
- Run `score` and `compare` as often as you like; they make no LLM calls.

## Ablation log

One row per agent change that was merged, all on `dev150` with the same model.
"Evidence on" is the dataset's hint text, which plays the role of a business glossary.
The gap between the two baseline rows estimates how much a semantic layer could
recover.

| Change | Run | Evidence | EX | EX (col-tol.) | Tables exact | Avg tokens | Avg LLM calls | Net vs prev (fixed/broken) |
|---|---|---|---:|---:|---:|---:|---:|---|
| Baseline (single-shot agent) | _to run_ | off | | | | | | — |
| Baseline (single-shot agent) | _to run_ | on | | | | | | — |
| Phase 1: profiled schema + descriptions (`--describe`) | _to run_ | off | | | | | | |

