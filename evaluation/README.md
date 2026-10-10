# SQL Agent Evaluation

Tests how well the SQL agent writes SQL. It asks the agent questions from the
BIRD mini-dev dataset (500 questions), runs the agent's SQL and the correct
("gold") SQL, and checks whether both return the same rows.

Only the SQL is tested, not the final text answer. The agent stops as soon as
its query works, so no tokens are spent on writing an answer.

## Setup (once)

1. Start Postgres: `docker compose up -d postgres` (the `bird` database must exist).
2. Install packages: `backend/venv/Scripts/pip install -r backend/requirements.txt`
3. Copy `evaluation/.env.example` to `evaluation/.env` and fill in an API key
   (`GEMINI_API_KEY` or `GROQ_API_KEY`).
4. Check that the dataset and database are OK. This uses no API calls:

   ```bash
   backend/venv/Scripts/python -m evaluation check-gold
   ```

## Run

Run all commands from the repo root.

```bash
# 50 random questions (mix of easy / medium / hard)
backend/venv/Scripts/python -m evaluation run --sample 50 --run-name my-test

# all 500 questions with Groq, max 10 requests per minute
backend/venv/Scripts/python -m evaluation run --provider groq --rpm 10 --run-name groq-full

# re-score a finished run without calling the LLM
backend/venv/Scripts/python -m evaluation score --run-name my-test
```

- **Stopped halfway?** Run the same command again with the same `--run-name`.
  It skips questions that are already done. Add `--fresh` to start over.
- **Out of quota?** The run stops on its own. Run it again later with the same `--run-name`.

Other useful options:

| Option | What it does |
|---|---|
| `--limit N` | only the first N questions |
| `--db-id X`, `--difficulty simple`, `--question-id 5` | pick specific questions |
| `--model X` | use a different model |
| `--no-evidence` | don't give the agent BIRD's hint text (closer to real users) |
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
