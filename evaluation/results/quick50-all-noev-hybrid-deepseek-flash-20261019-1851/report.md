# SQL Agent Evaluation: `quick50-all-noev-hybrid-deepseek-flash-20261019-1851`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (50 questions scored) | **Split:** `quick50`
- **Evidence hints:** off  | **Schema scope:** all BIRD tables  | **Schema format:** enriched + descriptions, auto prompt, hybrid (jina-embeddings-v5-text-small, 1024d) retrieval
- **Started:** 2026-10-19T18:51:15

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 14 | 27 | 9 | 50 |
| Accuracy (answer present; extra columns allowed) | 35.71 | 62.96 | 44.44 | 52.00 |
| EX strict (BIRD official) | 35.71 | 44.44 | 22.22 | 38.00 |
| Soft-F1 | 42.19 | 52.13 | 35.56 | 46.36 |
| Accuracy 95% CI | 16.3-61.2 | 44.2-78.5 | 18.9-73.3 | 38.5-65.2 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 3 | 33.33 | 0.00 | 31.78 |
| card_games | 5 | 20.00 | 20.00 | 26.42 |
| codebase_community | 5 | 100.00 | 100.00 | 100.00 |
| debit_card_specializing | 2 | 100.00 | 50.00 | 83.33 |
| european_football_2 | 5 | 40.00 | 40.00 | 20.00 |
| financial | 3 | 66.67 | 33.33 | 46.67 |
| formula_1 | 7 | 28.57 | 14.29 | 31.43 |
| student_club | 4 | 75.00 | 25.00 | 50.00 |
| superhero | 5 | 80.00 | 80.00 | 80.00 |
| thrombosis_prediction | 6 | 0.00 | 0.00 | 4.02 |
| toxicology | 5 | 80.00 | 60.00 | 68.00 |

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
| wrong_columns | 7 |
| wrong_values | 6 |
| wrong_tables | 5 |
| wrong_row_count | 4 |
| wrong_projection | 2 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (50 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 99.33 |
| Gold tables retrieved into the prompt (schema linking) | 99.33 |
| Table recall (pred SQL vs gold) | 95.33 |
| Table precision | 96.67 |
| Exact table set | 88.00 |
| Column recall | 87.01 |
| Column precision | 88.20 |
| Accuracy when table set is exact (n=44) | 56.82 |
| Accuracy when table set is wrong (n=6) | 16.67 |

## Cost & behaviour

- Tokens: 557,417 in / 10,871 out (avg 11,365.8 per question)
- Avg LLM calls per question: 1.42
- Latency: mean 2.874s, p50 2.529s, p95 4.865s
- Questions where the agent submitted more than once: 0 (0 ended correct)
- Tool calls: `submit_answer` 50, `run_sql` 29
- Answers by source: submit 50 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 18 (accuracy 33.33) vs. answered directly: 32 (accuracy 62.50)
- Avg SQL executions per question: 1.58; forced to submit: 0

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 10425.4 | 11747.9 | 11682.2 | 11365.8 |
| Avg LLM calls | 1.36 | 1.44 | 1.44 | 1.42 |
| Avg tool calls | 1.36 | 1.63 | 1.78 | 1.58 |
| Latency p50 (s) | 2.361 | 2.606 | 2.397 | 2.529 |
| Latency p95 (s) | 3.493 | 5.096 | 4.275 | 4.865 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
