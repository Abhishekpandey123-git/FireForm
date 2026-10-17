"""Provider selection and common inference entry point."""

import os

from app.core.config import LLAMA_CPP_MODEL, LLM_PROVIDER, OLLAMA_MODEL


def normalize_provider(provider: str | None = None) -> str:
    """Normalize provider aliases and reject unsupported values explicitly."""
    selected = (
        provider or os.getenv("LLM_PROVIDER", LLM_PROVIDER)
    ).strip().lower().replace("-", "_").replace(".", "_")

    aliases = {
        "ollama": "ollama",
        "llama_cpp": "llama_cpp",
        "llamacpp": "llama_cpp",
    }

    try:
        return aliases[selected]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported LLM_PROVIDER {provider or selected!r}; "
            "expected 'ollama' or 'llama_cpp'"
        ) from exc


def default_model(provider: str | None = None) -> str:
    """Return the configured model for the selected provider."""
    selected = normalize_provider(provider)

    if selected == "llama_cpp":
        return LLAMA_CPP_MODEL

    return OLLAMA_MODEL


def generate(prompt: str, schema: dict, model: str) -> str:
    """Dispatch inference to the configured provider."""
    selected = normalize_provider()

    if selected == "ollama":
        from .ollama import generate as provider_generate
    else:
        from .llama_cpp import generate as provider_generate

    return provider_generate(prompt, schema, model)
