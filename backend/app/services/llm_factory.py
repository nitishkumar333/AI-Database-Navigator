"""
Chat-model factory shared by the SQL agent and the offline evaluation suite.

Provider and model come from settings (LLM_PROVIDER, GEMINI_MODEL / GROQ_MODEL)
unless explicitly overridden by the caller.
"""
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings

SUPPORTED_PROVIDERS = ("gemini", "groq")


def default_model_for(provider: str) -> str:
    settings = get_settings()
    return settings.GROQ_MODEL if provider == "groq" else settings.GEMINI_MODEL


def create_chat_model(
    provider: str | None = None,
    model: str | None = None,
    *,
    temperature: float = 0,
    max_retries: int | None = None,
) -> BaseChatModel:
    settings = get_settings()
    # Only override the client's own retry default when explicitly asked to.
    extra = {} if max_retries is None else {"max_retries": max_retries}
    provider = (provider or settings.LLM_PROVIDER or "gemini").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Expected one of {SUPPORTED_PROVIDERS}."
        )
    model = model or default_model_for(provider)

    if provider == "groq":
        # Imported lazily so the Gemini-only deployment doesn't need the package.
        from langchain_groq import ChatGroq

        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY must be set to use the Groq provider.")
        return ChatGroq(
            model=model,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            **extra,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY must be set to use the Gemini provider.")
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=temperature,
        **extra,
    )
