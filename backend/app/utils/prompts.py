initial_suggestions_prompt = lambda schema_context: f"""You are a helpful data analyst assistant. Given the following database schema, suggest exactly 4 natural language questions that a user might want to ask about this data. The questions should be practical, insightful, and varied in complexity (some simple, some analytical).

DATABASE SCHEMA:
{schema_context}

RULES:
- Make questions specific to the actual table and column names in the schema
- Include a mix of: simple data retrieval, aggregation/counting, filtering, and analytical questions
- Keep questions concise (under 100 characters each)
- Do NOT include any SQL - only natural language questions"""

conversation_suggestions_prompt = lambda history_text: f"""You are a helpful data analyst assistant. Given the recent conversation below (each turn: the user's question, the SQL that answered it, and the assistant's reply), suggest exactly 3 relevant follow-up questions the user might want to ask next.

RECENT CONVERSATION:
{history_text}

RULES:
- Questions should be natural follow-ups to the conversation - drill deeper, compare, filter, or group the same data differently
- Only refer to tables and columns that appear in the SQL above
- Keep questions concise (under 100 characters each)
- Do NOT repeat questions already asked in the conversation
- Do NOT include any SQL - only natural language questions"""