import time
import re
import sqlparse
from typing import Dict, Any, Tuple
from sqlalchemy import text, inspect
import hashlib
from app.config import get_settings
from app.services.redis_client import redis_client

settings = get_settings()

class ValidateSqlQuery:
    def __init__(self, engine):
        self.engine = engine

    def validate_sql_query(self, sql_query: str) -> Dict[str, Any]:
        print("validate_sql_query", sql_query)
        sql_query = refine_sql_from_markdown(sql_query)
        print("refine_sql_from_markdown", sql_query)
        result = {
            'sql_query': sql_query,
            'validation_query': None,
            'validation_result': {}
        }
        
        # Step 1: Parse and validate the query structure
        is_safe, reason = self._is_query_safe(sql_query)
        
        if not is_safe:
            result['validation_result'] = {
                'is_safe': False,
                'explanation': reason,
                'schema_validated': False
            }
            return result
        
        # Step 2: Validate against database schema
        schema_valid, schema_reason, validation_query = self._validate_against_schema(sql_query)
        result['validation_query'] = validation_query
        print("schema_valid", schema_valid)
        print("schema_reason", schema_reason)
        print("validation_query", validation_query)
        if not schema_valid:
            result['validation_result'] = {
                'is_safe': False,
                'explanation': schema_reason,
                'schema_validated': False
            }
            return result
        
        result['validation_result'] = {
            'is_safe': True,
            'explanation': 'Query is safe to execute',
            'schema_validated': True
        }

        return result

    def _is_query_safe(self, sql_query: str) -> Tuple[bool, str]:
        """
        Check if the query is a safe read-only query.
        
        Returns:
            Tuple of (is_safe: bool, reason: str)
        """
        # Parse the SQL query
        parsed = sqlparse.parse(sql_query)
        
        if not parsed:
            return False, "Empty or invalid SQL query"
        
        # Get the first statement
        statement = parsed[0]
        
        # Get the query type
        query_type = statement.get_type()
        
        # List of allowed statement types (read-only operations)
        allowed_types = ['SELECT', 'UNKNOWN']  # UNKNOWN might be SELECT with CTEs
        
        # List of dangerous keywords that modify data
        dangerous_keywords = [
            'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
            'TRUNCATE', 'REPLACE', 'MERGE', 'GRANT', 'REVOKE',
            'EXEC', 'EXECUTE', 'CALL', 'INTO'
        ]
        
        # Check statement type
        if query_type not in allowed_types:
            return False, f"Query type '{query_type}' is not allowed. Only SELECT queries are permitted."
        
        # Check for dangerous keywords in the query
        query_upper = sql_query.upper()
        for keyword in dangerous_keywords:
            # Use word boundaries to avoid false positives (e.g., "DELETED_AT" column)
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, query_upper):
                return False, f"Dangerous keyword '{keyword}' detected. Query may modify data."
        
        # Check for SELECT INTO which can create tables
        if re.search(r'\bSELECT\b.*\bINTO\b', query_upper):
            return False, "SELECT INTO is not allowed as it creates new tables."
        
        # Additional security checks
        comment_pattern = r'(/\*.*?\*/|--.*?$)'
        if re.search(comment_pattern, sql_query, re.MULTILINE | re.DOTALL):
            # Allow comments but warn if they contain dangerous keywords
            comments = re.findall(comment_pattern, sql_query, re.MULTILINE | re.DOTALL)
            for comment in comments:
                for keyword in dangerous_keywords:
                    if keyword in comment.upper():
                        return False, f"Suspicious keyword '{keyword}' found in comment."
        
        return True, "Query structure is safe"

    def _validate_against_schema(self, sql_query: str) -> Tuple[bool, str, str]:
        """
        Validate the query against the actual database schema using EXPLAIN.
        
        Returns:
            Tuple of (is_valid: bool, reason: str, validation_query: str)
        """
        # Use EXPLAIN to validate without executing
        validation_query = f"EXPLAIN {sql_query}"
        
        try:
            with self.engine.connect() as connection:
                connection.execute(text(validation_query))
            
            return True, "Query validated against database schema", validation_query
        
        except Exception as e:
            error_msg = str(e)
            
            # Parse common PostgreSQL errors
            if 'relation' in error_msg.lower() and 'does not exist' in error_msg.lower():
                return False, f"Schema validation failed: Table does not exist - {error_msg}", validation_query
            elif 'column' in error_msg.lower() and 'does not exist' in error_msg.lower():
                return False, f"Schema validation failed: Column does not exist - {error_msg}", validation_query
            else:
                return False, f"Schema validation failed: {error_msg}", validation_query

    def _execute_sql_query(self, sql_query: str) -> dict:
        try:
            with self.engine.connect() as connection:
                query_result = connection.execute(text(sql_query))
                columns = list(query_result.keys())
                print("columns", columns)
                rows = [dict(zip(columns, row)) for row in query_result.fetchall()]
                print("rows", rows)

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }
        except Exception as error:
            return {
                "success": False,
                "error": str(error),
            }

def refine_sql_from_markdown(text_input: str) -> str:
    # Remove markdown code block syntax (```sql, ```, etc.)
    text_input = re.sub(r'```sql\s*', '', text_input)
    text_input = re.sub(r'```\s*', '', text_input)
    
    # Replace \n literals with actual spaces
    text_input = text_input.replace('\\n', ' ')
    
    # Replace actual newlines with spaces
    text_input = text_input.replace('\n', ' ')
    
    # Replace tabs with spaces
    text_input = text_input.replace('\t', ' ')
    
    # Remove extra whitespace (multiple spaces to single space)
    text_input = re.sub(r'\s+', ' ', text_input)
    
    # Clean up whitespace around parentheses and commas
    text_input = re.sub(r'\s*\(\s*', '(', text_input)
    text_input = re.sub(r'\s*\)\s*', ')', text_input)
    text_input = re.sub(r'\s*,\s*', ', ', text_input)
    text_input = re.sub(r'\s*;\s*', ';', text_input)
    
    # Trim leading/trailing whitespace
    text_input = text_input.strip()
    
    # Ensure semicolon at the end if missing
    if text_input and not text_input.endswith(';'):
        text_input += ';'

    return text_input

def get_all_table_names(engine) -> list:
    url_str = str(engine.url)
    url_hash = hashlib.md5(url_str.encode()).hexdigest()
    cache_key = f"tables:{url_hash}"
    
    cached_tables = redis_client.get(cache_key)
    if cached_tables:
        return cached_tables
        
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    
    redis_client.set(cache_key, all_tables, ex=3600)
    return all_tables

def get_schema_context(engine, table_names: list) -> str:
    """Build schema context string for the given tables."""
    url_str = str(engine.url)
    table_names_sorted = sorted(table_names)
    tables_hash = hashlib.md5((url_str + ":" + ",".join(table_names_sorted)).encode()).hexdigest()
    cache_key = f"schema:{tables_hash}"
    
    cached_schema = redis_client.get(cache_key)
    if cached_schema:
        return cached_schema

    inspector = inspect(engine)
    context_parts = []

    for table_name in table_names:
        try:
            columns = inspector.get_columns(table_name)
            pk = inspector.get_pk_constraint(table_name)
            fks = inspector.get_foreign_keys(table_name)

            col_lines = []
            pk_cols = pk.get("constrained_columns", []) if pk else []
            for col in columns:
                flags = []
                if col["name"] in pk_cols:
                    flags.append("PRIMARY KEY")
                if not col.get("nullable", True):
                    flags.append("NOT NULL")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                col_lines.append(f"    {col['name']} {col['type']}{flag_str}")

            fk_lines = []
            for fk in fks:
                fk_lines.append(
                    f"    FOREIGN KEY ({', '.join(fk['constrained_columns'])}) "
                    f"REFERENCES {fk['referred_table']}({', '.join(fk['referred_columns'])})"
                )

            table_def = f"  TABLE {table_name}:\n" + "\n".join(col_lines)
            if fk_lines:
                table_def += "\n  Foreign Keys:\n" + "\n".join(fk_lines)

            context_parts.append(table_def)
        except Exception:
            context_parts.append(f"  TABLE {table_name}: (unable to read schema)")

    schema_str = "\n\n".join(context_parts)
    redis_client.set(cache_key, schema_str, ex=3600)
    return schema_str



def execute_raw_sql(engine, sql: str) -> dict:
    """Execute user-edited SQL query."""
    start_time = time.time()
    
    refined_sql = refine_sql_from_markdown(sql)
    validation = ValidateSqlQuery(engine)
    result = validation.validate_sql_query(refined_sql)

    if not (result['validation_result'].get('is_safe') and result['validation_result'].get('schema_validated')):
        latency_ms = (time.time() - start_time) * 1000
        return {
            "success": False,
            "sql": refined_sql,
            "error": result['validation_result'].get('explanation', 'Validation Failed'),
            "latency_ms": round(latency_ms, 2),
        }

    try:
        with engine.connect() as connection:
            query_result = connection.execute(text(result['sql_query']))
            columns = list(query_result.keys())
            rows = [dict(zip(columns, row)) for row in query_result.fetchall()]

        latency_ms = (time.time() - start_time) * 1000
        return {
            "success": True,
            "sql": result['sql_query'],
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "latency_ms": round(latency_ms, 2),
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {
            "success": False,
            "sql": result['sql_query'],
            "error": str(e),
            "latency_ms": round(latency_ms, 2),
        }
