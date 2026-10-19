"""The reply step: short prompt, no schema, no tools, its own model."""
from types import SimpleNamespace

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.services.agent import graph, prompts
from app.services.agent.tools import SUBMIT_ANSWER


class _Recording(GenericFakeChatModel):
    seen: list = []

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, *args, **kwargs)


def _state(rows=({"id": 1}, {"id": 2})):
    artifact = {"kind": SUBMIT_ANSWER, "success": True, "sql": "SELECT 1",
                "assumptions": "first two by id", "rows": list(rows)}
    return {
        "messages": [HumanMessage(content="give detail about any 2 users"),
                     AIMessage(content="", tool_calls=[{"name": SUBMIT_ANSWER, "args": {}, "id": "c1"}]),
                     ToolMessage(content='{"rows": [1, 2]}', tool_call_id="c1",
                                 name=SUBMIT_ANSWER, artifact=artifact)],
        "last_user_input": "give detail about any 2 users",
        "answer": artifact,
    }


def test_reply_uses_reply_llm_and_short_prompt():
    reply = _Recording(messages=iter([AIMessage(content="Two users: Danielle and Lisa.")]))
    agent = _Recording(messages=iter([]))     # must not be called
    ctx = SimpleNamespace(llm=agent, reply_llm=reply, turn_id="t", schema_context="SCHEMA")
    out = graph._write_reply(ctx, _state())
    assert out["messages"][0].content == "Two users: Danielle and Lisa."
    system, user = reply.seen[-1]
    assert system.content == prompts.REPLY_PROMPT and "SCHEMA" not in user.content
    assert '{"rows": [1, 2]}' in user.content
    assert "first two by id" not in user.content     # the UI shows it next to the rows


def test_reply_mentions_assumptions_for_empty_result():
    reply = _Recording(messages=iter([AIMessage(content="No users found.")]))
    ctx = SimpleNamespace(llm=reply, reply_llm=None, turn_id="t")
    graph._write_reply(ctx, _state(rows=()))
    assert "first two by id" in reply.seen[-1][1].content


def test_reply_failure_falls_back():
    broken = _Recording(messages=iter([]))    # raises when called
    ctx = SimpleNamespace(llm=broken, reply_llm=None, turn_id="t")
    out = graph._write_reply(ctx, _state())
    assert out["messages"][0].content == prompts.REPLY_FALLBACK
