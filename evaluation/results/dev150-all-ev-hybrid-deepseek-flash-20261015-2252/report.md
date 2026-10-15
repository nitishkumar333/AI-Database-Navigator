# SQL Agent Evaluation: `dev150-all-ev-hybrid-deepseek-flash-20261015-2252`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (150 questions scored) | **Split:** `dev150`
- **Evidence hints:** on  | **Schema scope:** all BIRD tables  | **Schema format:** enriched + descriptions, auto prompt, hybrid (jina-embeddings-v5-text-small, 1024d) retrieval
- **Started:** 2026-10-15T22:52:13

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 43 | 77 | 30 | 150 |
| Accuracy (answer present; extra columns allowed) | 83.72 | 70.13 | 56.67 | 71.33 |
| EX strict (BIRD official) | 79.07 | 61.04 | 43.33 | 62.67 |
| Soft-F1 | 81.14 | 65.34 | 52.00 | 67.20 |
| Accuracy 95% CI | 70.0-91.9 | 59.1-79.2 | 39.2-72.6 | 63.6-78.0 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 8 | 37.50 | 37.50 | 36.90 |
| card_games | 16 | 75.00 | 62.50 | 68.02 |
| codebase_community | 14 | 78.57 | 71.43 | 79.05 |
| debit_card_specializing | 9 | 88.89 | 66.67 | 79.63 |
| european_football_2 | 16 | 68.75 | 62.50 | 70.42 |
| financial | 10 | 50.00 | 30.00 | 35.01 |
| formula_1 | 20 | 65.00 | 55.00 | 57.41 |
| student_club | 14 | 85.71 | 78.57 | 80.61 |
| superhero | 16 | 87.50 | 87.50 | 95.62 |
| thrombosis_prediction | 15 | 60.00 | 53.33 | 48.64 |
| toxicology | 12 | 75.00 | 66.67 | 71.67 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 107 |
| wrong_result | 43 |

Of the correct answers, 13 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_tables | 11 |
| wrong_values | 11 |
| wrong_columns | 10 |
| wrong_projection | 7 |
| wrong_row_count | 4 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (150 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 99.33 |
| Gold tables retrieved into the prompt (schema linking) | 99.33 |
| Table recall (pred SQL vs gold) | 95.11 |
| Table precision | 97.89 |
| Exact table set | 86.00 |
| Column recall | 90.67 |
| Column precision | 93.69 |
| Accuracy when table set is exact (n=129) | 75.19 |
| Accuracy when table set is wrong (n=21) | 47.62 |

## Cost & behaviour

- Tokens: 1,481,042 in / 32,758 out (avg 10,092.0 per question)
- Avg LLM calls per question: 1.35
- Latency: mean 3.09s, p50 2.667s, p95 5.365s
- Questions where the agent submitted more than once: 4 (3 ended correct)
- Tool calls: `submit_answer` 154, `run_sql` 67, `find_values` 6, `describe_tables` 1
- Answers by source: submit 150 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 33 (accuracy 54.55) vs. answered directly: 117 (accuracy 76.07)
- Avg SQL executions per question: 1.47; forced to submit: 1

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 8568.7 | 10058.9 | 12360.4 | 10092.0 |
| Avg LLM calls | 1.21 | 1.34 | 1.57 | 1.35 |
| Avg tool calls | 1.3 | 1.53 | 1.8 | 1.52 |
| Latency p50 (s) | 2.186 | 2.703 | 3.284 | 2.667 |
| Latency p95 (s) | 3.76 | 5.247 | 7.645 | 5.365 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
