# SQL Agent Evaluation: `dev150-test-2`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (150 questions scored) | **Split:** `dev150`
- **Evidence hints:** on  | **Schema scope:** per-database  | **Schema format:** enriched + descriptions, auto prompt
- **Started:** 2026-10-14T19:46:57

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 43 | 77 | 30 | 150 |
| Accuracy (answer present; extra columns allowed) | 86.05 | 66.23 | 60.00 | 70.67 |
| EX strict (BIRD official) | 79.07 | 54.55 | 46.67 | 60.00 |
| Soft-F1 | 81.89 | 60.92 | 55.33 | 65.81 |
| Accuracy 95% CI | 72.7-93.4 | 55.1-75.8 | 42.3-75.4 | 62.9-77.4 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 8 | 75.00 | 62.50 | 75.83 |
| card_games | 16 | 81.25 | 75.00 | 72.08 |
| codebase_community | 14 | 71.43 | 64.29 | 71.90 |
| debit_card_specializing | 9 | 77.78 | 55.56 | 68.52 |
| european_football_2 | 16 | 62.50 | 56.25 | 63.04 |
| financial | 10 | 40.00 | 20.00 | 26.67 |
| formula_1 | 20 | 60.00 | 40.00 | 50.03 |
| student_club | 14 | 85.71 | 71.43 | 78.23 |
| superhero | 16 | 87.50 | 87.50 | 95.62 |
| thrombosis_prediction | 15 | 60.00 | 53.33 | 48.52 |
| toxicology | 12 | 75.00 | 66.67 | 71.67 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 106 |
| wrong_result | 44 |

Of the correct answers, 16 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_tables | 15 |
| wrong_values | 12 |
| wrong_columns | 8 |
| wrong_projection | 6 |
| wrong_row_count | 3 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (150 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 100.00 |
| Table recall (pred SQL vs gold) | 94.67 |
| Table precision | 96.89 |
| Exact table set | 84.00 |
| Column recall | 90.57 |
| Column precision | 92.33 |
| Accuracy when table set is exact (n=126) | 76.98 |
| Accuracy when table set is wrong (n=24) | 37.50 |

## Cost & behaviour

- Tokens: 999,176 in / 27,701 out (avg 6,845.8 per question)
- Avg LLM calls per question: 1.27
- Latency: mean 1.843s, p50 1.515s, p95 3.315s
- Questions where the agent submitted more than once: 2 (1 ended correct)
- Tool calls: `submit_answer` 152, `run_sql` 45, `find_values` 17
- Answers by source: submit 150 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 23 (accuracy 60.87) vs. answered directly: 127 (accuracy 72.44)
- Avg SQL executions per question: 1.3; forced to submit: 1

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 6257.4 | 6866.5 | 7636.3 | 6845.8 |
| Avg LLM calls | 1.16 | 1.27 | 1.43 | 1.27 |
| Avg tool calls | 1.21 | 1.43 | 1.73 | 1.43 |
| Latency p50 (s) | 1.332 | 1.565 | 1.73 | 1.515 |
| Latency p95 (s) | 2.73 | 3.404 | 4.654 | 3.315 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
