import chromadb
from app.config import get_settings

settings = get_settings()

_client = None
_collection_cache = {}


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _client


def get_collection(conn_id: int):
    collection_name = f"schema_conn_{conn_id}"
    if collection_name not in _collection_cache:
        client = get_chroma_client()
        _collection_cache[collection_name] = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection_cache[collection_name]


def embed_knowledge(conn_id: int, kb_entry):
    """Embed knowledge base entry into ChromaDB for RAG retrieval."""
    collection = get_collection(conn_id)

    # Build document text from metadata
    col_desc_text = ""
    if kb_entry.column_descriptions:
        col_desc_text = "\n".join(
            [f"  - {col}: {desc}" for col, desc in kb_entry.column_descriptions.items()]
        )

    sample_q_text = ""
    if kb_entry.sample_queries:
        sample_q_text = "\nSample queries:\n" + "\n".join(
            [f"  - {q}" for q in kb_entry.sample_queries]
        )

    document = f"""Table: {kb_entry.table_name}
Description: {kb_entry.table_description}
Columns:
{col_desc_text}
{sample_q_text}"""

    doc_id = f"table_{kb_entry.table_name}"

    # Upsert document
    collection.upsert(
        ids=[doc_id],
        documents=[document],
        metadatas=[{"table_name": kb_entry.table_name, "connection_id": conn_id}],
    )

    return True


def search_relevant_tables(conn_id: int, query: str, n_results: int = 5):
    """Search for relevant tables based on natural language query."""
    collection = get_collection(conn_id)

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
        )
        return results
    except Exception:
        return {"documents": [[]], "metadatas": [[]]}
