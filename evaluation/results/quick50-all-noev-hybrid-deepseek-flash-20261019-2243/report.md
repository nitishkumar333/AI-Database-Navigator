# SQL Agent Evaluation: `quick50-all-noev-hybrid-deepseek-flash-20261019-2243`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (50 questions scored) | **Split:** `quick50`
- **Evidence hints:** off  | **Schema scope:** all BIRD tables  | **Schema format:** enriched + descriptions, auto prompt, hybrid (jina-embeddings-v5-text-small, 1024d) retrieval
- **Started:** 2026-10-19T22:43:29

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 14 | 27 | 9 | 50 |
| Accuracy (answer present; extra columns allowed) | 42.86 | 62.96 | 44.44 | 54.00 |
| EX strict (BIRD official) | 42.86 | 48.15 | 33.33 | 44.00 |
| Soft-F1 | 46.70 | 56.32 | 36.67 | 50.09 |
| Accuracy 95% CI | 21.4-67.4 | 44.2-78.5 | 18.9-73.3 | 40.4-67.0 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 3 | 33.33 | 0.00 | 35.56 |
| card_games | 5 | 20.00 | 20.00 | 22.32 |
| codebase_community | 5 | 100.00 | 100.00 | 100.00 |
| debit_card_specializing | 2 | 100.00 | 50.00 | 83.33 |
| european_football_2 | 5 | 40.00 | 40.00 | 40.00 |
| financial | 3 | 66.67 | 33.33 | 46.67 |
| formula_1 | 7 | 42.86 | 28.57 | 40.00 |
| student_club | 4 | 75.00 | 50.00 | 57.14 |
| superhero | 5 | 80.00 | 80.00 | 80.00 |
| thrombosis_prediction | 6 | 0.00 | 0.00 | 3.48 |
| toxicology | 5 | 80.00 | 80.00 | 70.00 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 27 |
| wrong_result | 23 |

Of the correct answers, 5 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_columns | 7 |
| wrong_values | 6 |
| wrong_tables | 5 |
| wrong_projection | 3 |
| wrong_row_count | 2 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (50 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 99.33 |
| Gold tables retrieved into the prompt (schema linking) | 99.33 |
| Table recall (pred SQL vs gold) | 96.00 |
| Table precision | 97.67 |
| Exact table set | 88.00 |
| Column recall | 87.58 |
| Column precision | 88.82 |
| Accuracy when table set is exact (n=44) | 59.09 |
| Accuracy when table set is wrong (n=6) | 16.67 |

## Cost & behaviour

- Tokens: 547,970 in / 10,747 out (avg 11,174.3 per question)
- Avg LLM calls per question: 1.38
- Latency: mean 3.298s, p50 2.916s, p95 6.441s
- Questions where the agent submitted more than once: 0 (0 ended correct)
- Tool calls: `submit_answer` 50, `run_sql` 24, `search_schema` 1, `describe_tables` 1
- Answers by source: submit 50 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 16 (accuracy 18.75) vs. answered directly: 34 (accuracy 70.59)
- Avg SQL executions per question: 1.48; forced to submit: 0

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 9289.6 | 11434.6 | 13325.6 | 11174.3 |
| Avg LLM calls | 1.21 | 1.41 | 1.56 | 1.38 |
| Avg tool calls | 1.21 | 1.59 | 1.78 | 1.52 |
| Latency p50 (s) | 2.696 | 2.939 | 3.24 | 2.916 |
| Latency p95 (s) | 5.065 | 6.441 | 6.901 | 6.441 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
