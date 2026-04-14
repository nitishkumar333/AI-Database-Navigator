from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import auth, connections, schema, knowledge, query, history

app = FastAPI(
    title="AI Data Analyst Platform",
    description="Natural Language → SQL",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(connections.router)
app.include_router(schema.router)
app.include_router(knowledge.router)
app.include_router(query.router)
app.include_router(history.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"message": "AI Data Analyst Platform API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}
