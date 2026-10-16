"""Ollama adapter using its native /api/generate endpoint."""

import requests

from app.core.config import OLLAMA_HOST, OLLAMA_TIMEOUT
from .options import OPTIONS


def generate(prompt: str, schema: dict, model: str) -> str:
    """Generate schema-constrained JSON with Ollama and return response text."""
    payload = {
        "model": model,
        "prompt": prompt,
        "format": schema,
        "stream": False,
        "think": False,
        "options": OPTIONS,
    }
    response = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json=payload,
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Ollama response was not a JSON object")
    text = body.get("response", "")
    if not isinstance(text, str):
        raise ValueError("Ollama response did not contain text")
    return text
