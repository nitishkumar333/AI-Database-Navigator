# SQL Agent Evaluation: `dev150-full-nolink`

- **Provider / model:** deepseek / `deepseek-flash`
- **Dataset:** bird_minidev_postgresql.csv (150 questions scored) | **Split:** `dev150`
- **Evidence hints:** on  | **Schema scope:** all BIRD tables  | **Schema format:** enriched + descriptions, auto prompt, keyword retrieval
- **Started:** 2026-10-14T22:44:44

## Accuracy (%)

| Metric | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Count | 43 | 77 | 30 | 150 |
| Accuracy (answer present; extra columns allowed) | 79.07 | 64.94 | 60.00 | 68.00 |
| EX strict (BIRD official) | 74.42 | 55.84 | 50.00 | 60.00 |
| Soft-F1 | 80.13 | 60.73 | 52.01 | 64.55 |
| Accuracy 95% CI | 64.8-88.6 | 53.8-74.7 | 42.3-75.4 | 60.2-74.9 |

A question is correct when the gold answer is present in the output: extra columns and a different column order are allowed, missing or wrong rows are not. Strict EX (BIRD's official metric) also requires the exact columns.

Two runs whose confidence intervals overlap heavily are not reliably different; use `python -m evaluation compare` for a paired test on the same questions.

## By database

| db_id | n | Accuracy | EX strict | Soft-F1 |
|---|---:|---:|---:|---:|
| california_schools | 8 | 37.50 | 25.00 | 46.69 |
| card_games | 16 | 81.25 | 81.25 | 75.02 |
| codebase_community | 14 | 71.43 | 64.29 | 68.33 |
| debit_card_specializing | 9 | 88.89 | 66.67 | 79.63 |
| european_football_2 | 16 | 56.25 | 56.25 | 66.88 |
| financial | 10 | 50.00 | 30.00 | 35.00 |
| formula_1 | 20 | 55.00 | 35.00 | 44.19 |
| student_club | 14 | 85.71 | 78.57 | 73.81 |
| superhero | 16 | 87.50 | 87.50 | 95.62 |
| thrombosis_prediction | 15 | 53.33 | 46.67 | 47.18 |
| toxicology | 12 | 75.00 | 75.00 | 71.67 |

## Outcome breakdown

| Status | Count |
|---|---:|
| correct | 102 |
| wrong_result | 48 |

Of the correct answers, 12 have extra columns or another column order (strict EX would count them as wrong).

## Why questions were missed

Heuristic first-cause per missed question (see `evaluation/linking.py`).

| Category | Count |
|---|---:|
| wrong_values | 13 |
| wrong_tables | 11 |
| wrong_columns | 9 |
| wrong_projection | 9 |
| wrong_row_count | 6 |

## Schema linking (%)

Tables/columns referenced by the predicted SQL vs the gold SQL (150 questions with a prediction).

| Metric | Value |
|---|---:|
| Gold tables present in agent context | 96.00 |
| Gold tables retrieved into the prompt (schema linking) | 0.00 |
| Table recall (pred SQL vs gold) | 95.33 |
| Table precision | 97.78 |
| Exact table set | 88.00 |
| Column recall | 90.93 |
| Column precision | 92.42 |
| Accuracy when table set is exact (n=132) | 71.97 |
| Accuracy when table set is wrong (n=18) | 38.89 |

## Cost & behaviour

- Tokens: 1,717,946 in / 34,525 out (avg 11,683.1 per question)
- Avg LLM calls per question: 2.31
- Latency: mean 2.72s, p50 2.399s, p95 4.616s
- Questions where the agent submitted more than once: 3 (2 ended correct)
- Tool calls: `describe_tables` 157, `submit_answer` 153, `run_sql` 30, `search_schema` 14, `find_values` 4
- Answers by source: submit 150 (`exploration` = budget ran out, last `run_sql` used; `none` = no SQL)
- Questions where the agent explored first: 18 (accuracy 44.44) vs. answered directly: 132 (accuracy 71.21)
- Avg SQL executions per question: 1.22; forced to submit: 0

| | simple | moderate | challenging | total |
|---|---:|---:|---:|---:|
| Avg tokens | 10251.7 | 11556.2 | 14060.8 | 11683.1 |
| Avg LLM calls | 2.16 | 2.25 | 2.67 | 2.31 |
| Avg tool calls | 2.23 | 2.31 | 2.8 | 2.39 |
| Latency p50 (s) | 2.228 | 2.38 | 2.614 | 2.399 |
| Latency p95 (s) | 3.554 | 4.513 | 8.543 | 4.616 |

Status legend: `correct` = gold answer present in the output; `wrong_result` = ran but rows differ; `no_sql` = agent neither submitted nor ran a successful query; `pred_error`/`pred_timeout` = generated SQL failed on re-execution; `agent_error` = graph/LLM error; `gold_error` = gold SQL failed (excluded from accuracy).
