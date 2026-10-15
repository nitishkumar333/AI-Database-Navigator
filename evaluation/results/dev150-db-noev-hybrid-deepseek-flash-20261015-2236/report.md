# SQL Agent Evaluation: `dev150-db-noev-hybrid-deepseek-flash-20261015-2236`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (150 questions scored) | **Split:** `dev150`
- **Evidence hints:** off  | **Schema scope:** per-database  | **Schema format:** enriched + descriptions, auto prompt, hybrid (jina-embeddings-v5-text-small, 1024d) retrieval
- **Started:** 2026-10-15T22:36:35

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 43 | 77 | 30 | 150 |
| Accuracy (answer present; extra columns allowed) | 65.12 | 54.55 | 43.33 | 55.33 |
| EX strict (BIRD official) | 58.14 | 46.75 | 30.00 | 46.67 |
| Soft-F1 | 66.35 | 50.21 | 35.37 | 51.87 |
| Accuracy 95% CI | 50.2-77.6 | 43.5-65.2 | 27.4-60.8 | 47.3-63.1 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 8 | 50.00 | 37.50 | 59.17 |
| card_games | 16 | 50.00 | 50.00 | 44.77 |
| codebase_community | 14 | 78.57 | 71.43 | 72.14 |
| debit_card_specializing | 9 | 77.78 | 55.56 | 68.52 |
| european_football_2 | 16 | 50.00 | 43.75 | 57.29 |
| financial | 10 | 30.00 | 20.00 | 26.67 |
| formula_1 | 20 | 50.00 | 25.00 | 42.43 |
| student_club | 14 | 71.43 | 64.29 | 60.38 |
| superhero | 16 | 68.75 | 68.75 | 73.75 |
| thrombosis_prediction | 15 | 13.33 | 13.33 | 16.54 |
| toxicology | 12 | 75.00 | 66.67 | 54.91 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 83 |
| wrong_result | 67 |

Of the correct answers, 13 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_columns | 24 |
| wrong_tables | 20 |
| wrong_values | 9 |
| wrong_projection | 8 |
| wrong_row_count | 6 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (150 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 100.00 |
| Gold tables retrieved into the prompt (schema linking) | - |
| Table recall (pred SQL vs gold) | 92.78 |
| Table precision | 95.94 |
| Exact table set | 80.67 |
| Column recall | 84.89 |
| Column precision | 89.10 |
| Accuracy when table set is exact (n=121) | 61.16 |
| Accuracy when table set is wrong (n=29) | 31.03 |

## Cost & behaviour

- Tokens: 1,622,514 in / 47,150 out (avg 11,131.1 per question)
- Avg LLM calls per question: 1.95
- Latency: mean 2.844s, p50 2.544s, p95 7.437s
- Questions where the agent submitted more than once: 1 (0 ended correct)
- Tool calls: `run_sql` 176, `submit_answer` 150, `find_values` 39, `search_schema` 16, `describe_tables` 4
- Answers by source: submit 149, exploration 1 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 83 (accuracy 42.17) vs. answered directly: 67 (accuracy 71.64)
- Avg SQL executions per question: 2.13; forced to submit: 7

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 9219.3 | 11967.5 | 11724.7 | 11131.1 |
| Avg LLM calls | 1.7 | 2.03 | 2.13 | 1.95 |
| Avg tool calls | 1.88 | 2.75 | 3.07 | 2.57 |
| Latency p50 (s) | 2.204 | 2.546 | 2.737 | 2.544 |
| Latency p95 (s) | 3.489 | 8.057 | 9.059 | 7.437 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
