"""
ChatDeepSeek that sends reasoning back to the API.

In thinking mode, DeepSeek rejects a request with tools (HTTP 400) unless every
earlier assistant message carries its `reasoning_content`. langchain-deepseek
stores that field in `additional_kwargs` on responses but drops it from the
next request, so a tool loop fails on its second model call. This subclass puts
it back.
"""
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek


class ReasoningChatDeepSeek(ChatDeepSeek):
    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # The payload has one dict per input message, in the same order.
        ai_messages = [m for m in self._convert_input(input_).to_messages() if isinstance(m, AIMessage)]
        assistant_dicts = [m for m in payload["messages"] if m["role"] == "assistant"]
        for message, ai in zip(assistant_dicts, ai_messages):
            reasoning = ai.additional_kwargs.get("reasoning_content")
            if reasoning:
                message["reasoning_content"] = reasoning
        return payload
