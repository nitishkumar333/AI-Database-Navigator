import os
import sqlite3
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langgraph.prebuilt import tools_condition
from langgraph.graph.message import AnyMessage, add_messages
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import ToolNode
from langchain_core.runnables import RunnableLambda
from google.api_core.exceptions import ResourceExhausted
from fastapi import HTTPException
from app.services.validate_sql import SafeSqlExecutor

from app.config import get_settings
settings = get_settings()
load_dotenv()

def create_tool_node_with_fallback(tools: list) -> dict:
    return ToolNode(tools).with_fallbacks(
        [RunnableLambda(handle_tool_error)], exception_key="error"
    )

def handle_tool_error(state) -> dict:
    error = state.get("error")
    tool_calls = state["messages"][-1].tool_calls
    return {
        "messages": [
            ToolMessage(
                content=f"Error: {repr(error)}\n please fix your mistakes.",
                tool_call_id=tc["id"],
            )
            for tc in tool_calls
        ]
    }

def create_sql_tool(agent_instance):
    @tool
    def execute_sql_query(sql_query: str) -> str:
        """
        Executes a SQL query safely against the database.
        RULES:
        1. sql_query must be a valid PostgreSQL SELECT query
        2. Use proper table and column names from the schema
        3. Add appropriate LIMIT clause if the query could return many rows
        4. Prioritize and include image URL columns (e.g., image_url, image, thumbnail) whenever present in the queried tables

        Args:
            sql_query: Single SQL query string to execute

        Returns:
            Result of sql query execution on database
        """

        executor = SafeSqlExecutor(agent_instance.engine, max_rows=50)
        result = executor.run(sql_query)

        if not result.success:
            return f"Error: {result.error}"

        # Only store state for queries that actually ran.
        agent_instance.generated_sql = result.sql
        agent_instance.columns = result.columns
        agent_instance.rows = result.rows

        return result.to_llm_string()

    return execute_sql_query

class SQLAgent:
    def __init__(self, engine, schema_context):
        self.engine = engine
        self.system_prompt = self.generate_system_prompt(schema_context)
        self.columns = []
        self.rows = []
        self.generated_sql = ""

        self.execute_sql_query = create_sql_tool(self)
        self.workflow = self.build_workflow()

    class UserState(TypedDict):
        messages: Annotated[list[AnyMessage], add_messages]
        last_user_input: str | None
    
    def generate_system_prompt(self, schema_context):
        return f"""You are an AI agent with capability to generate SQL queries. You can use tool `execute_sql_query` to generate a PostgreSQL SELECT query and answer the user's question based on the query result.

CRITICAL QUERY INSTRUCTIONS:
1. Always prioritize and include columns containing image URLs (such as `image_url`, `image`, `img`, `thumbnail`, `photo`, `picture`, `avatar`, etc.) in the SELECT list whenever the queried tables or joined tables contain them, so that the final SQL query result includes image links.
2. When using GROUP BY or aggregations on tables with image columns, ensure the image column is preserved in the output (e.g., include it in the GROUP BY or use MAX/MIN or an appropriate aggregate).
3. Generate only valid PostgreSQL SELECT queries. Do not generate DDL/DML statements (INSERT, UPDATE, DELETE, DROP, etc.).
4. Use clear column aliases where helpful and add an appropriate LIMIT clause if many rows could be returned.
5. In your final natural language response, provide a clear, concise summary of the findings.

DATABASE SCHEMA:
{schema_context}"""
    
    def generate_response(self, state: UserState) -> dict:
        system_prompt = self.system_prompt
        assistant_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("placeholder", "{conversation}"),
            ]
        )

        llm = ChatGoogleGenerativeAI(
            model=getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0,
        )
        runnable_llm = assistant_prompt | llm.bind_tools([self.execute_sql_query])
        response = runnable_llm.invoke({"conversation": state["messages"]})
        return {**state,"messages": response}
    
    def build_workflow(self):
        graph = StateGraph(self.UserState)
        graph.add_node("generate_response", self.generate_response)
        graph.add_node("tools", create_tool_node_with_fallback([self.execute_sql_query]))
        graph.set_entry_point("generate_response")
        graph.add_conditional_edges("generate_response", tools_condition)
        graph.add_edge("tools", "generate_response")
        checkpoint_path = getattr(settings, "CHECKPOINT_DB_PATH", "checkpoints.sqlite")
        dir_name = os.path.dirname(checkpoint_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
        memory = SqliteSaver(conn)
        return graph.compile(checkpointer=memory)


    def run_query(self, user_input: str, conversation_id: str = None):
        human_message = HumanMessage(content=user_input)
        messages = [human_message]
        initial_state = {
            "messages": messages,
            "last_user_input": user_input,
            "conversation_id": conversation_id
        } 
        config = { "configurable": { "thread_id": conversation_id} }
        try:
            state = self.workflow.invoke(initial_state, config)
        except ResourceExhausted as e:
            raise HTTPException(status_code=429, detail="LLM API rate limit exceeded. Please try again later.")
        except Exception as e:
            print(f"Error executing SQL agent workflow: {e}")
            import traceback
            traceback.print_exc()
            is_rate_limit = "429" in str(e) or "ResourceExhausted" in str(type(e).__name__)
            error_message = "Error: LLM rate limit exceeded. Please try again later." if is_rate_limit else f"Error: {e}"
            return {
                "success": False,
                "question": user_input,
                "generated_sql": self.generated_sql or "",
                "columns": self.columns or [],
                "rows": self.rows or [],
                "error": error_message,
                "response_text": error_message,
            }
        return {
            "success": True,
            "question": user_input,
            "generated_sql": self.generated_sql,
            "columns": self.columns,
            "rows": self.rows,
            "response_text": state['messages'][-1].content
        }