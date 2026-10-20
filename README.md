# SQLNav — AI Database Navigator

Ask questions about your PostgreSQL database in plain English. SQLNav turns them into SQL, runs them, and explains the results.

- **Backend:** FastAPI + LangGraph SQL agent (Gemini, Groq or DeepSeek), PostgreSQL (with pgvector), Redis
- **Frontend:** Next.js 14 + Tailwind
- **Evaluation:** a benchmark harness that scores the agent on the BIRD mini-dev dataset

For how things work inside, see [backend/BACKEND_TECHNICAL_DOCS.md](backend/BACKEND_TECHNICAL_DOCS.md) and [frontend/FRONTEND_TECHNICAL_DOCS.md](frontend/FRONTEND_TECHNICAL_DOCS.md).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose (easiest way)
- For running without Docker: Python 3.11+, Node.js 20+, PostgreSQL 16 with pgvector, Redis 7
- An API key for at least one LLM provider: Gemini, Groq or DeepSeek

## Quick start (Docker)

```bash
git clone https://github.com/nitishkumar333/AI-Database-Navigator.git
cd AI-Database-Navigator
cp .env.example .env
```

Edit `.env` and set at least:

| Variable | What to put |
|---|---|
| `SECRET_KEY` | Any long random string |
| `ENCRYPTION_KEY` | A Fernet key (see below) |
| `LLM_PROVIDER` | `gemini`, `groq` or `deepseek` |
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `DEEPSEEK_API_KEY` | The key for the provider you picked |

Generate an `ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then start everything:

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 (docs at `/docs`) |

Compose also seeds a sample `shop` database, which guest users can query right away.

## Running without Docker

You still need PostgreSQL and Redis. The simplest way is to start only those from Compose:

```bash
docker compose up -d postgres redis
```

### Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` (copy the values from the root `.env.example`) and add the database URL:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/sqlnav
```

Optionally seed the sample `shop` database, then start the server:

```bash
python seed_shop.py
uvicorn main:app --reload
```

The API runs at http://localhost:8000.

Run the tests with:

```bash
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at http://localhost:3000. It talks to `http://localhost:8000` by default; set `NEXT_PUBLIC_API_URL` to point it elsewhere.

## Evaluation

The `evaluation/` package asks the agent questions from the [BIRD mini-dev](https://github.com/bird-bench/mini_dev) dataset, runs its SQL against the correct SQL, and reports accuracy, failure causes and token cost.

### Setup

1. Start Postgres: `docker compose up -d postgres`. A `bird` database with the BIRD mini-dev tables must exist.
2. Install the backend packages (see [Backend](#backend)).
3. Copy `evaluation/.env.example` to `evaluation/.env` and set `BIRD_DB_URL` and an LLM API key. Anything not set there falls back to `backend/.env`.
4. Check the dataset and database (no LLM calls):

   ```bash
   backend/venv/Scripts/python -m evaluation check-gold --split dev150
   ```

On macOS/Linux, use `backend/venv/bin/python` instead of `backend/venv/Scripts/python`.

### Run

Run these from the repo root:

```bash
# quick 30-question smoke test
backend/venv/Scripts/python -m evaluation run --provider groq --split smoke30

# 150-question benchmark, max 20 requests per minute
backend/venv/Scripts/python -m evaluation run --provider groq --split dev150 --rpm 20

# compare two runs (no LLM calls)
backend/venv/Scripts/python -m evaluation compare <baseline-run> <new-run>
```

Results go to `evaluation/results/<run-name>/`. Start with `report.md`.

Runs use LLM quota, so iterate on `smoke30` and run `dev150` once per finished change. For all options, splits and how to read the report, see [evaluation/README.md](evaluation/README.md).

## Project structure

```
backend/       FastAPI app, SQL agent, schema indexing
frontend/      Next.js web app
evaluation/    BIRD benchmark harness and results
docker-compose.yml
.env.example
```
