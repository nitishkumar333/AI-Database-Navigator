# SQL Agent Evaluation

Tests how well the SQL agent writes SQL. It asks the agent questions from the
BIRD mini-dev dataset (500 questions), runs the agent's SQL and the correct
("gold") SQL, and checks whether both return the same rows.

Only the SQL is tested, not the final text answer. The agent may explore
first (`search_schema`, `describe_tables`, `find_values`, `run_sql`); the query
it submits with `submit_answer` is what gets scored, and the run stops there, so
no tokens are spent on writing an answer. Exploratory queries are never scored,
except as a fallback when the agent runs out of budget without submitting
(`answer_source: exploration` in the record).

## Setup (once)

1. Start Postgres: `docker compose up -d postgres` (the `bird` database must exist).
2. Install packages: `backend/venv/Scripts/pip install -r backend/requirements.txt`
3. Copy `evaluation/.env.example` to `evaluation/.env` and fill in an API key
   (`GEMINI_API_KEY`, `GROQ_API_KEY` or `DEEPSEEK_API_KEY`).
4. Check that the dataset and database are OK. This uses no API calls:

   ```bash
   backend/venv/Scripts/python -m evaluation check-gold --split dev150
   ```

## Run

Run all commands from the repo root.

```bash
# the frozen 30-question smoke set (cheap; use while iterating)
backend/venv/Scripts/python -m evaluation run --provider groq --split smoke30

# the frozen 150-question benchmark (use before merging a change)
backend/venv/Scripts/python -m evaluation run --provider groq --split dev150 --rpm 20

# all 500 questions with Groq, max 10 requests per minute
backend/venv/Scripts/python -m evaluation run --provider groq --rpm 10

# re-score a finished run without calling the LLM
backend/venv/Scripts/python -m evaluation score --run-name <run>

# compare runs on the questions they share (first = baseline), no LLM calls
backend/venv/Scripts/python -m evaluation compare <baseline-run> <new-run> --out my-change.md
```

**Run names.** Without `--run-name`, a run is named after the settings that
change its results, so the folder name says what was measured:

    {split}-{scope}-{evidence}-{retrieval}[-basic|-nodesc][-think]-{model}-{YYYYMMDD-HHMM}
    dev150-all-noev-hybrid-deepseek-flash-20261015-2243

| Part | Values |
|---|---|
| split | `smoke30`, `quick50`, `dev150`, ... (`custom` for other filters) |
| scope | `db` = the question's database, `all` = all 75 BIRD tables (`--full-schema`) |
| evidence | `ev` = BIRD hints given, `noev` = `--no-evidence` |
| retrieval | `hybrid` (Jina embeddings), `trigram` (no Jina key), `keyword` (`--no-retrieval`) |
| flags | `basic` = `--schema-format basic`, `nodesc` = `--no-describe`, `think` = DeepSeek thinking mode |

Pass `--run-name` only to resume a run or to give it a name of your own.

- **Stopped halfway?** Run it again with `--run-name <its folder name>`.
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
| `--no-evidence` | don't give the agent BIRD's hint text (closer to real users) |
| `--schema-format basic` | the schema format from before profiling, to measure what profiling adds (default `enriched`) |
| `--no-describe` | leave out the LLM-written table/column descriptions. By default the agent gets the same schema as in production, descriptions included. They are generated the way the backend does (one LLM call per table, with the run's model) the first time a table is missing, then saved in `data/bird_descriptions.json` and reused by every later run, whatever the model. Commit that file once it's complete |
| `--output-rows N` | result rows saved per question (default 100, 0 = all) |
| `--full-schema` | give the agent all 75 BIRD tables instead of the question's database. That schema (~90k chars) is over `AGENT_FULL_SCHEMA_MAX_CHARS`, so the prompt holds the table list and **schema linking** adds the tables retrieved for each question: the way to test retrieval on BIRD, whose single databases are small enough to go in the prompt whole |
| `--no-retrieval` | search the schema by keywords over the profile instead of the retrieval index (the pre-Phase-3 behaviour), for comparison |

## Schema retrieval

Before the first question, a run builds or updates the retrieval index of the
BIRD tables in the app database (`eval:bird:described`; needs pgvector there,
see the backend docs). With `JINA_API_KEY` set, every table and column
document is embedded once (~870 short texts), later runs reuse the vectors;
without it the index uses trigram + value matching. `config.json` records the
method as `retrieval` (`hybrid (model, dims)`, `trigram` or `keyword`).

Schema linking can be measured without the agent, so it costs no LLM tokens
(with Jina: one query embedding per question):

```bash
# are the gold SQL's tables among the tables linked into the prompt?
backend/venv/Scripts/python -m evaluation link-recall --split dev150 --full-schema --no-evidence
backend/venv/Scripts/python -m evaluation link-recall --split dev150 --full-schema --no-retrieval --show-misses 20
```

It prints, per difficulty, the share of questions with **every** gold table
linked, the share of gold tables linked, the average number of tables linked,
how many come from other BIRD databases, and the prompt text added. In a run
with `--full-schema`, the report's schema-linking table shows the same
`linked_recall` per question, next to `context_recall` (linked + described).

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
| **Accuracy** | The main score, and what `correct` means: % of questions where the gold answer is present in the agent's output. Some subset of its columns, in any order, must give exactly the gold rows. Extra columns (a name next to the asked-for value, an image URL) and a different column order are fine; missing, extra or wrong rows are not. |
| **EX strict** | BIRD's official metric: the rows must match with exactly the gold columns, in order. Kept to compare with published BIRD numbers. |
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

- **Accuracy 95% CI**: the range the true accuracy probably lies in. At 30 questions it
  is about ±17 points, and at 150 questions about ±8. Two runs whose ranges
  overlap a lot are not reliably different.
- **Why questions were missed**: one heuristic cause per missed question,
  checked in this order:

  | Category | Meaning | What usually fixes it |
  |---|---|---|
  | `wrong_tables` | Used different tables than gold | Schema descriptions, retrieval (schema linking) |
  | `wrong_columns` | Same tables, missed a column gold uses | Column descriptions, sample values |
  | `wrong_projection` | Different number of output columns | Prompt rules on output shape |
  | `wrong_row_count` | Same shape, different row count | Filter values, join fan-out, LIMIT logic |
  | `wrong_values` | Same shape and row count, different values | Business definitions (glossary), type casts |
  | `no_sql`, `pred_error`, ... | See the status table above | |

- **Schema linking**: compares the tables and columns used by the predicted SQL
  with those used by the gold SQL. Aliases (`T1`, `T2`) and unqualified columns
  are resolved against the real schema with sqlglot.
  - *Gold tables present in agent context* is 100% when the schema fits in the
    prompt (`AGENT_FULL_SCHEMA_MAX_CHARS`; true for every single BIRD database).
    When it doesn't (e.g. `--full-schema`), the prompt lists tables only and this
    counts the tables the agent described, so it measures retrieval. Each record's
    `schema_prompt` says which case applied.
  - *Accuracy when table set is exact/wrong* shows how much accuracy is lost to
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
| `quick50` | 50 (a subset of `dev150`) | Comparing different configurations |
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
"Evidence on" is BIRD's hint text, which plays the role of a business glossary.
The gap between the two baseline rows estimates how much a semantic layer could
recover.

| Change | Run | Evidence | Accuracy | EX strict | Tables exact | Avg tokens | Avg LLM calls | Net vs prev (fixed/broken) |
|---|---|---|---:|---:|---:|---:|---:|---|
| Baseline (single-shot agent) | _to run_ | off | | | | | | — |
| Baseline (single-shot agent) | _to run_ | on | | | | | | — |
| Phase 1: profiled schema + descriptions (default) | _to run_ | off | | | | | | |

