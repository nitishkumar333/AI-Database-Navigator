# SQL Agent Evaluation: `deepseek-deepseek-flash-20261014-121106`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (30 questions scored) | **Split:** `smoke30`
- **Evidence hints:** off  | **Schema scope:** per-database  | **Schema format:** enriched + descriptions
- **Started:** 2026-10-14T12:11:06

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 8 | 16 | 6 | 30 |
| EX (BIRD official) | 62.50 | 31.25 | 50.00 | 43.33 |
| EX (column-tolerant) | 75.00 | 56.25 | 50.00 | 60.00 |
| Soft-F1 | 67.50 | 42.39 | 43.33 | 49.27 |
| EX 95% CI | 30.6-86.3 | 14.2-55.6 | 18.8-81.2 | 27.4-60.8 |

Two runs whose EX confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | EX | EX (col-tolerant) | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 1 | 0.00 | 100.00 | 40.00 |
| card_games | 4 | 75.00 | 75.00 | 75.30 |
| codebase_community | 2 | 50.00 | 50.00 | 50.00 |
| debit_card_specializing | 2 | 50.00 | 100.00 | 83.33 |
| european_football_2 | 4 | 25.00 | 25.00 | 30.00 |
| financial | 1 | 0.00 | 0.00 | 0.00 |
| formula_1 | 5 | 40.00 | 60.00 | 50.00 |
| student_club | 2 | 50.00 | 100.00 | 70.00 |
| superhero | 4 | 75.00 | 75.00 | 75.00 |
| thrombosis_prediction | 3 | 0.00 | 0.00 | 0.00 |
| toxicology | 2 | 50.00 | 100.00 | 30.18 |

## Outcome breakdown

| Status | Count |
|---|---:|
| wrong_result | 17 |
| correct | 13 |

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_tables | 7 |
| extra_columns | 5 |
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
| EX when table set is exact (n=22) | 59.09 |
| EX when table set is wrong (n=8) | 0.00 |

## Cost & behaviour

- Tokens: 135,051 in / 3,595 out (avg 4,621.5 per question)
- Avg LLM calls per question: 1.03
- Latency: mean 1.767s, p50 1.713s, p95 2.743s
- Questions where the agent retried after a tool error: 2 (0 ended correct)
- Tool calls: `execute_sql_query` 32

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 4502.5 | 4714.8 | 4531.7 | 4621.5 |
| Avg LLM calls | 1.0 | 1.06 | 1.0 | 1.03 |
| Avg tool calls | 1.0 | 1.12 | 1.0 | 1.07 |
| Latency p50 (s) | 1.385 | 1.717 | 1.76 | 1.713 |
| Latency p95 (s) | 1.975 | 3.74 | 2.743 | 2.743 |

Status legend: `correct` = EX match; `wrong_result` = ran but rows differ; `no_sql` = agent never produced a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
