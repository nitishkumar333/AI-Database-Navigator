import re
from fastapi import HTTPException


BLOCKED_PATTERNS = [
    r'\bDROP\b',
    r'\bDELETE\b',
    r'\bUPDATE\b',
    r'\bALTER\b',
    r'\bTRUNCATE\b',
    r'\bINSERT\b',
    r'\bCREATE\b',
    r'\bGRANT\b',
    r'\bREVOKE\b',
    r'\bEXEC\b',
    r'\bEXECUTE\b',
]

MAX_ROWS = 1000
QUERY_TIMEOUT_SECONDS = 30


def validate_sql(sql: str) -> str:
    """Validate SQL query for safety. Returns cleaned SQL or raises HTTPException."""
    cleaned = sql.strip().rstrip(';')

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            raise HTTPException(
                status_code=400,
                detail=f"Blocked: SQL contains forbidden operation matching '{pattern}'"
            )

    # Ensure it's a SELECT query
    if not re.match(r'^\s*(SELECT|WITH|EXPLAIN)\b', cleaned, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed"
        )

    # Add LIMIT if not present
    if not re.search(r'\bLIMIT\b', cleaned, re.IGNORECASE):
        cleaned = f"{cleaned} LIMIT {MAX_ROWS}"

    return cleaned


def sanitize_table_name(name: str) -> str:
    """Sanitize table name to prevent SQL injection."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)
