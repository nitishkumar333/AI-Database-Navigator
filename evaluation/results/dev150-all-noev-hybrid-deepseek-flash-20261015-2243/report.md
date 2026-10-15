# SQL Agent Evaluation: `dev150-all-noev-hybrid-deepseek-flash-20261015-2243`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (150 questions scored) | **Split:** `dev150`
- **Evidence hints:** off  | **Schema scope:** all BIRD tables  | **Schema format:** enriched + descriptions, auto prompt, hybrid (jina-embeddings-v5-text-small, 1024d) retrieval
- **Started:** 2026-10-15T22:43:02

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 43 | 77 | 30 | 150 |
| Accuracy (answer present; extra columns allowed) | 67.44 | 55.84 | 26.67 | 53.33 |
| EX strict (BIRD official) | 65.12 | 48.05 | 13.33 | 46.00 |
| Soft-F1 | 69.47 | 53.22 | 22.96 | 51.83 |
| Accuracy 95% CI | 52.5-79.5 | 44.7-66.4 | 14.2-44.5 | 45.4-61.1 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 8 | 37.50 | 25.00 | 46.67 |
| card_games | 16 | 56.25 | 50.00 | 56.27 |
| codebase_community | 14 | 71.43 | 71.43 | 71.67 |
| debit_card_specializing | 9 | 66.67 | 44.44 | 57.41 |
| european_football_2 | 16 | 43.75 | 37.50 | 51.04 |
| financial | 10 | 30.00 | 20.00 | 26.67 |
| formula_1 | 20 | 55.00 | 45.00 | 51.61 |
| student_club | 14 | 71.43 | 64.29 | 60.72 |
| superhero | 16 | 68.75 | 68.75 | 73.22 |
| thrombosis_prediction | 15 | 13.33 | 13.33 | 16.62 |
| toxicology | 12 | 66.67 | 50.00 | 49.49 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 80 |
| wrong_result | 70 |

Of the correct answers, 11 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_tables | 24 |
| wrong_columns | 21 |
| wrong_values | 11 |
| wrong_row_count | 9 |
| wrong_projection | 5 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (150 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 98.89 |
| Gold tables retrieved into the prompt (schema linking) | 98.22 |
| Table recall (pred SQL vs gold) | 91.78 |
| Table precision | 96.33 |
| Exact table set | 78.00 |
| Column recall | 84.04 |
| Column precision | 90.31 |
| Accuracy when table set is exact (n=117) | 60.68 |
| Accuracy when table set is wrong (n=33) | 27.27 |

## Cost & behaviour

- Tokens: 2,453,720 in / 50,581 out (avg 16,695.3 per question)
- Avg LLM calls per question: 2.06
- Latency: mean 3.839s, p50 3.415s, p95 8.242s
- Questions where the agent submitted more than once: 0 (0 ended correct)
- Tool calls: `run_sql` 210, `submit_answer` 150, `search_schema` 29, `describe_tables` 11, `find_values` 9
- Answers by source: submit 150 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 96 (accuracy 41.67) vs. answered directly: 54 (accuracy 74.07)
- Avg SQL executions per question: 2.37; forced to submit: 8

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 13022.3 | 15916.1 | 23959.9 | 16695.3 |
| Avg LLM calls | 1.67 | 1.99 | 2.8 | 2.06 |
| Avg tool calls | 1.91 | 2.71 | 3.93 | 2.73 |
| Latency p50 (s) | 2.581 | 3.415 | 4.29 | 3.415 |
| Latency p95 (s) | 5.713 | 8.011 | 9.598 | 8.242 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
