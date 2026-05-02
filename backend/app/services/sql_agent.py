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
from .validate_sql import ValidateSqlQuery
from langgraph.prebuilt import ToolNode
from langchain_core.runnables import RunnableLambda

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

        Args:
            sql_query: Single SQL query string to execute

        Returns:
            Result of sql query execution on database
        """
        try:
            validation = ValidateSqlQuery(agent_instance.engine)
            result = validation.validate_sql_query(sql_query)
        except Exception as e:
            return str(e)

        if result['validation_result'].get('is_safe') and result['validation_result'].get('schema_validated'):
            result = validation._execute_sql_query(sql_query)
            agent_instance.generated_sql = result.get('sql_query', sql_query)
            agent_instance.columns = result.get('columns', [])
            agent_instance.rows = result.get('rows', [])
            return result
        else:
            return result['validation_result'].get('explanation', "SQL query is not safe to execute.")

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
            model="gemini-2.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0,
        )
        runnable_llm = assistant_prompt | llm.bind_tools([self.execute_sql_query])

        try:
            response = runnable_llm.invoke({"conversation": state["messages"]})
            print("response", response)
        except Exception as e:
            print("error", e)
            return {**state,"messages": AIMessage(content=str(e))}
        return {**state,"messages": response}
    
    def build_workflow(self):
        print("build_workflow")
        graph = StateGraph(self.UserState)
        graph.add_node("generate_response", self.generate_response)
        graph.add_node("tools", create_tool_node_with_fallback([self.execute_sql_query]))
        graph.set_entry_point("generate_response")
        graph.add_conditional_edges("generate_response", tools_condition)
        graph.add_edge("tools", "generate_response")
        conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
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
        except Exception as e:
            print("error", e)
            return {
                "success": False,
                "question": user_input,
                "generated_sql": "",
                "columns": [],
                "rows": [],
                "response_text": "Error: LLM rate limit exceeded."
            }
        return {
            "success": True,
            "question": user_input,
            "generated_sql": self.generated_sql,
            "columns": self.columns,
            "rows": self.rows,
            "response_text": state['messages'][-1].content
        }