# SQL Agent Evaluation: `phase2-smoke30`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (30 questions scored) | **Split:** `smoke30`
- **Evidence hints:** off  | **Schema scope:** per-database  | **Schema format:** enriched + descriptions, full prompt
- **Started:** 2026-10-14T16:43:52

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 8 | 16 | 6 | 30 |
| Accuracy (answer present; extra columns allowed) | 75.00 | 56.25 | 33.33 | 56.67 |
| EX strict (BIRD official) | 62.50 | 37.50 | 16.67 | 40.00 |
| Soft-F1 | 71.32 | 40.87 | 26.67 | 46.15 |
| Accuracy 95% CI | 40.9-92.8 | 33.2-76.9 | 9.7-70.0 | 39.2-72.6 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 1 | 100.00 | 0.00 | 0.00 |
| card_games | 4 | 50.00 | 50.00 | 50.00 |
| codebase_community | 2 | 50.00 | 50.00 | 50.00 |
| debit_card_specializing | 2 | 100.00 | 50.00 | 83.33 |
| european_football_2 | 4 | 25.00 | 25.00 | 30.00 |
| financial | 1 | 0.00 | 0.00 | 0.00 |
| formula_1 | 5 | 60.00 | 20.00 | 47.45 |
| student_club | 2 | 100.00 | 100.00 | 100.00 |
| superhero | 4 | 75.00 | 75.00 | 75.00 |
| thrombosis_prediction | 3 | 0.00 | 0.00 | 0.00 |
| toxicology | 2 | 100.00 | 50.00 | 30.27 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 17 |
| wrong_result | 13 |

Of the correct answers, 5 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_columns | 6 |
| wrong_tables | 6 |
| wrong_projection | 1 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (30 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 100.00 |
| Table recall (pred SQL vs gold) | 86.11 |
| Table precision | 94.44 |
| Exact table set | 66.67 |
| Column recall | 78.62 |
| Column precision | 86.94 |
| Accuracy when table set is exact (n=20) | 65.00 |
| Accuracy when table set is wrong (n=10) | 40.00 |

## Cost & behaviour

- Tokens: 398,280 in / 10,522 out (avg 13,626.7 per question)
- Avg LLM calls per question: 2.4
- Latency: mean 3.295s, p50 2.993s, p95 5.378s
- Questions where the agent submitted more than once: 0 (0 ended correct)
- Tool calls: `run_sql` 53, `submit_answer` 30, `find_values` 6, `search_schema` 4, `describe_tables` 2
- Answers by source: submit 30 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 28 (accuracy 53.57) vs. answered directly: 2 (accuracy 100.00)
- Avg SQL executions per question: 2.73; forced to submit: 1

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 10907.4 | 14942.2 | 13744.7 | 13626.7 |
| Avg LLM calls | 2.0 | 2.62 | 2.33 | 2.4 |
| Avg tool calls | 2.12 | 3.69 | 3.17 | 3.17 |
| Latency p50 (s) | 2.212 | 3.214 | 3.508 | 2.993 |
| Latency p95 (s) | 2.641 | 8.809 | 4.536 | 5.378 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
