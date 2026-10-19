# SQL Agent Evaluation: `quick50-all-noev-hybrid-deepseek-flash-20261019-1756`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (50 questions scored) | **Split:** `quick50`
- **Evidence hints:** off  | **Schema scope:** all BIRD tables  | **Schema format:** enriched + descriptions, auto prompt, hybrid (jina-embeddings-v5-text-small, 1024d) retrieval
- **Started:** 2026-10-19T17:56:00

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 14 | 27 | 9 | 50 |
| Accuracy (answer present; extra columns allowed) | 42.86 | 59.26 | 44.44 | 52.00 |
| EX strict (BIRD official) | 42.86 | 44.44 | 11.11 | 38.00 |
| Soft-F1 | 40.26 | 48.33 | 31.85 | 43.10 |
| Accuracy 95% CI | 21.4-67.4 | 40.7-75.5 | 18.9-73.3 | 38.5-65.2 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 3 | 0.00 | 0.00 | 13.33 |
| card_games | 5 | 20.00 | 20.00 | 22.56 |
| codebase_community | 5 | 100.00 | 100.00 | 100.00 |
| debit_card_specializing | 2 | 100.00 | 50.00 | 83.33 |
| european_football_2 | 5 | 40.00 | 40.00 | 20.00 |
| financial | 3 | 66.67 | 33.33 | 46.67 |
| formula_1 | 7 | 28.57 | 14.29 | 25.71 |
| student_club | 4 | 75.00 | 25.00 | 45.83 |
| superhero | 5 | 80.00 | 80.00 | 80.00 |
| thrombosis_prediction | 6 | 16.67 | 16.67 | 4.29 |
| toxicology | 5 | 80.00 | 40.00 | 61.33 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 26 |
| wrong_result | 24 |

Of the correct answers, 7 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_columns | 8 |
| wrong_tables | 6 |
| wrong_values | 5 |
| wrong_row_count | 3 |
| wrong_projection | 2 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (50 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 99.33 |
| Gold tables retrieved into the prompt (schema linking) | 99.33 |
| Table recall (pred SQL vs gold) | 93.33 |
| Table precision | 97.33 |
| Exact table set | 86.00 |
| Column recall | 85.21 |
| Column precision | 88.27 |
| Accuracy when table set is exact (n=43) | 58.14 |
| Accuracy when table set is wrong (n=7) | 14.29 |

## Cost & behaviour

- Tokens: 580,184 in / 11,721 out (avg 11,838.1 per question)
- Avg LLM calls per question: 1.44
- Latency: mean 2.899s, p50 2.383s, p95 5.298s
- Questions where the agent submitted more than once: 0 (0 ended correct)
- Tool calls: `submit_answer` 50, `run_sql` 30, `search_schema` 1
- Answers by source: submit 50 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 20 (accuracy 35.00) vs. answered directly: 30 (accuracy 63.33)
- Avg SQL executions per question: 1.6; forced to submit: 0

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 11380.6 | 12017.6 | 12011.2 | 11838.1 |
| Avg LLM calls | 1.43 | 1.44 | 1.44 | 1.44 |
| Avg tool calls | 1.43 | 1.67 | 1.78 | 1.62 |
| Latency p50 (s) | 2.362 | 2.383 | 2.733 | 2.383 |
| Latency p95 (s) | 4.018 | 5.813 | 5.298 | 5.298 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
