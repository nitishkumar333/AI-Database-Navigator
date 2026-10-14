# SQL Agent Evaluation: `deepseek-deepseek-flash-20261014-121106`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (30 questions scored) | **Split:** `smoke30`
- **Evidence hints:** off  | **Schema scope:** per-database  | **Schema format:** enriched + descriptions, full prompt
- **Started:** 2026-10-14T12:11:06

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 8 | 16 | 6 | 30 |
| Accuracy (answer present; extra columns allowed) | 75.00 | 56.25 | 50.00 | 60.00 |
| EX strict (BIRD official) | 62.50 | 31.25 | 50.00 | 43.33 |
| Soft-F1 | 67.50 | 42.31 | 43.33 | 49.23 |
| Accuracy 95% CI | 40.9-92.8 | 33.2-76.9 | 18.8-81.2 | 42.3-75.4 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 1 | 100.00 | 0.00 | 40.00 |
| card_games | 4 | 75.00 | 75.00 | 75.00 |
| codebase_community | 2 | 50.00 | 50.00 | 50.00 |
| debit_card_specializing | 2 | 100.00 | 50.00 | 83.33 |
| european_football_2 | 4 | 25.00 | 25.00 | 30.00 |
| financial | 1 | 0.00 | 0.00 | 0.00 |
| formula_1 | 5 | 60.00 | 40.00 | 50.00 |
| student_club | 2 | 100.00 | 50.00 | 70.00 |
| superhero | 4 | 75.00 | 75.00 | 75.00 |
| thrombosis_prediction | 3 | 0.00 | 0.00 | 0.00 |
| toxicology | 2 | 100.00 | 50.00 | 30.18 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 18 |
| wrong_result | 12 |

Of the correct answers, 5 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_tables | 7 |
| wrong_columns | 4 |
| wrong_projection | 1 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (30 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 100.00 |
| Table recall (pred SQL vs gold) | 91.67 |
| Table precision | 95.56 |
| Exact table set | 73.33 |
| Column recall | 83.69 |
| Column precision | 86.08 |
| Accuracy when table set is exact (n=22) | 77.27 |
| Accuracy when table set is wrong (n=8) | 12.50 |

## Cost & behaviour

- Tokens: 135,051 in / 3,595 out (avg 4,621.5 per question)
- Avg LLM calls per question: 1.03
- Latency: mean 1.767s, p50 1.713s, p95 2.743s
- Questions where the agent submitted more than once: 2 (0 ended correct)
- Tool calls: `execute_sql_query` 32

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 4502.5 | 4714.8 | 4531.7 | 4621.5 |
| Avg LLM calls | 1.0 | 1.06 | 1.0 | 1.03 |
| Avg tool calls | 1.0 | 1.12 | 1.0 | 1.07 |
| Latency p50 (s) | 1.385 | 1.717 | 1.76 | 1.713 |
| Latency p95 (s) | 1.975 | 3.74 | 2.743 | 2.743 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
