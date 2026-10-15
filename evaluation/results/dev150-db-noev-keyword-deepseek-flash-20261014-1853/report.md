# SQL Agent Evaluation: `dev150-db-noev-keyword-deepseek-flash-20261014-1853`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (150 questions scored) | **Split:** `dev150`
- **Evidence hints:** off  | **Schema scope:** per-database  | **Schema format:** enriched + descriptions, auto prompt
- **Started:** 2026-10-14T18:53:09

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 43 | 77 | 30 | 150 |
| Accuracy (answer present; extra columns allowed) | 67.44 | 57.14 | 43.33 | 57.33 |
| EX strict (BIRD official) | 62.79 | 50.65 | 30.00 | 50.00 |
| Soft-F1 | 67.97 | 53.64 | 37.06 | 54.43 |
| Accuracy 95% CI | 52.5-79.5 | 46.0-67.6 | 27.4-60.8 | 49.3-65.0 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 8 | 50.00 | 37.50 | 50.83 |
| card_games | 16 | 56.25 | 56.25 | 50.59 |
| codebase_community | 14 | 78.57 | 71.43 | 75.71 |
| debit_card_specializing | 9 | 77.78 | 55.56 | 68.52 |
| european_football_2 | 16 | 43.75 | 43.75 | 53.12 |
| financial | 10 | 30.00 | 20.00 | 25.00 |
| formula_1 | 20 | 55.00 | 40.00 | 50.79 |
| student_club | 14 | 71.43 | 64.29 | 60.63 |
| superhero | 16 | 68.75 | 68.75 | 73.75 |
| thrombosis_prediction | 15 | 20.00 | 20.00 | 17.27 |
| toxicology | 12 | 83.33 | 66.67 | 72.36 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 86 |
| wrong_result | 64 |

Of the correct answers, 11 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_columns | 25 |
| wrong_tables | 19 |
| wrong_values | 10 |
| wrong_projection | 6 |
| wrong_row_count | 4 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (150 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 100.00 |
| Table recall (pred SQL vs gold) | 92.44 |
| Table precision | 96.56 |
| Exact table set | 79.33 |
| Column recall | 83.72 |
| Column precision | 88.78 |
| Accuracy when table set is exact (n=119) | 62.18 |
| Accuracy when table set is wrong (n=31) | 38.71 |

## Cost & behaviour

- Tokens: 1,530,636 in / 41,741 out (avg 10,482.5 per question)
- Avg LLM calls per question: 1.9
- Latency: mean 2.709s, p50 2.434s, p95 6.773s
- Questions where the agent submitted more than once: 0 (0 ended correct)
- Tool calls: `submit_answer` 150, `run_sql` 150, `find_values` 41, `search_schema` 14, `describe_tables` 7
- Answers by source: submit 150 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 79 (accuracy 44.30) vs. answered directly: 71 (accuracy 71.83)
- Avg SQL executions per question: 2.0; forced to submit: 6

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 8928.7 | 10382.8 | 12965.5 | 10482.5 |
| Avg LLM calls | 1.7 | 1.86 | 2.3 | 1.9 |
| Avg tool calls | 1.88 | 2.45 | 3.07 | 2.41 |
| Latency p50 (s) | 2.22 | 2.468 | 2.808 | 2.434 |
| Latency p95 (s) | 4.36 | 6.576 | 8.342 | 6.773 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
