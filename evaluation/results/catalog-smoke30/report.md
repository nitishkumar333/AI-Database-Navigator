# SQL Agent Evaluation: `catalog-smoke30`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (30 questions scored) | **Split:** `smoke30`
- **Evidence hints:** off  | **Schema scope:** per-database  | **Schema format:** enriched + descriptions, catalog prompt
- **Started:** 2026-10-14T17:17:39

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 8 | 16 | 6 | 30 |
| Accuracy (answer present; extra columns allowed) | 75.00 | 62.50 | 50.00 | 63.33 |
| EX strict (BIRD official) | 62.50 | 43.75 | 50.00 | 50.00 |
| Soft-F1 | 71.32 | 50.87 | 43.33 | 54.82 |
| Accuracy 95% CI | 40.9-92.8 | 38.6-81.5 | 18.8-81.2 | 45.5-78.1 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 1 | 100.00 | 0.00 | 66.67 |
| card_games | 4 | 75.00 | 75.00 | 75.00 |
| codebase_community | 2 | 50.00 | 50.00 | 50.00 |
| debit_card_specializing | 2 | 100.00 | 50.00 | 83.33 |
| european_football_2 | 4 | 25.00 | 25.00 | 32.50 |
| financial | 1 | 0.00 | 0.00 | 0.00 |
| formula_1 | 5 | 60.00 | 20.00 | 44.12 |
| student_club | 2 | 100.00 | 100.00 | 100.00 |
| superhero | 4 | 75.00 | 75.00 | 75.00 |
| thrombosis_prediction | 3 | 33.33 | 33.33 | 33.33 |
| toxicology | 2 | 100.00 | 100.00 | 30.27 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 19 |
| wrong_result | 11 |

Of the correct answers, 4 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_tables | 5 |
| wrong_columns | 4 |
| wrong_values | 1 |
| wrong_projection | 1 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (30 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 96.11 |
| Table recall (pred SQL vs gold) | 90.56 |
| Table precision | 94.44 |
| Exact table set | 76.67 |
| Column recall | 82.63 |
| Column precision | 86.28 |
| Accuracy when table set is exact (n=23) | 73.91 |
| Accuracy when table set is wrong (n=7) | 28.57 |

## Cost & behaviour

- Tokens: 381,287 in / 12,193 out (avg 13,116.0 per question)
- Avg LLM calls per question: 3.27
- Latency: mean 4.566s, p50 3.766s, p95 9.911s
- Questions where the agent submitted more than once: 0 (0 ended correct)
- Tool calls: `run_sql` 44, `describe_tables` 30, `submit_answer` 30, `search_schema` 11, `find_values` 3
- Answers by source: submit 30 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 22 (accuracy 59.09) vs. answered directly: 8 (accuracy 75.00)
- Avg SQL executions per question: 2.43; forced to submit: 2

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 8149.1 | 14749.9 | 15381.5 | 13116.0 |
| Avg LLM calls | 2.5 | 3.56 | 3.5 | 3.27 |
| Avg tool calls | 2.75 | 4.25 | 4.67 | 3.93 |
| Latency p50 (s) | 3.263 | 4.253 | 4.491 | 3.766 |
| Latency p95 (s) | 3.925 | 11.449 | 9.911 | 9.911 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
