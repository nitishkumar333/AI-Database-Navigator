# SQL Agent Evaluation: `dev150-phase3-full`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (150 questions scored) | **Split:** `dev150`
- **Evidence hints:** on  | **Schema scope:** all BIRD tables  | **Schema format:** enriched + descriptions, auto prompt, hybrid (jina-embeddings-v5-text-small, 1024d) retrieval
- **Started:** 2026-10-14T22:42:26

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 43 | 77 | 30 | 150 |
| Accuracy (answer present; extra columns allowed) | 83.72 | 68.83 | 56.67 | 70.67 |
| EX strict (BIRD official) | 76.74 | 61.04 | 46.67 | 62.67 |
| Soft-F1 | 81.34 | 66.61 | 50.11 | 67.53 |
| Accuracy 95% CI | 70.0-91.9 | 57.8-78.1 | 39.2-72.6 | 62.9-77.4 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 8 | 37.50 | 25.00 | 46.67 |
| card_games | 16 | 81.25 | 75.00 | 74.27 |
| codebase_community | 14 | 78.57 | 71.43 | 79.05 |
| debit_card_specializing | 9 | 88.89 | 66.67 | 79.63 |
| european_football_2 | 16 | 62.50 | 56.25 | 63.88 |
| financial | 10 | 60.00 | 40.00 | 45.00 |
| formula_1 | 20 | 55.00 | 45.00 | 47.69 |
| student_club | 14 | 78.57 | 78.57 | 73.81 |
| superhero | 16 | 87.50 | 87.50 | 95.62 |
| thrombosis_prediction | 15 | 66.67 | 60.00 | 60.40 |
| toxicology | 12 | 75.00 | 66.67 | 70.83 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 106 |
| wrong_result | 44 |

Of the correct answers, 12 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_tables | 11 |
| wrong_values | 11 |
| wrong_columns | 9 |
| wrong_projection | 7 |
| wrong_row_count | 6 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (150 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 99.33 |
| Gold tables retrieved into the prompt (schema linking) | 99.33 |
| Table recall (pred SQL vs gold) | 94.94 |
| Table precision | 97.89 |
| Exact table set | 86.00 |
| Column recall | 90.98 |
| Column precision | 93.72 |
| Accuracy when table set is exact (n=129) | 74.42 |
| Accuracy when table set is wrong (n=21) | 47.62 |

## Cost & behaviour

- Tokens: 1,314,604 in / 27,373 out (avg 8,946.5 per question)
- Avg LLM calls per question: 1.26
- Latency: mean 2.78s, p50 2.424s, p95 4.841s
- Questions where the agent submitted more than once: 5 (2 ended correct)
- Tool calls: `submit_answer` 155, `run_sql` 39, `describe_tables` 3, `find_values` 3
- Answers by source: submit 150 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 19 (accuracy 52.63) vs. answered directly: 131 (accuracy 73.28)
- Avg SQL executions per question: 1.29; forced to submit: 1

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 7848.3 | 8712.5 | 11121.4 | 8946.5 |
| Avg LLM calls | 1.16 | 1.22 | 1.5 | 1.26 |
| Avg tool calls | 1.19 | 1.31 | 1.6 | 1.33 |
| Latency p50 (s) | 2.077 | 2.424 | 3.055 | 2.424 |
| Latency p95 (s) | 3.641 | 4.599 | 5.246 | 4.841 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
