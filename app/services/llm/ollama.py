"""Ollama adapter using its native /api/generate endpoint."""

import requests

from app.core.config import OLLAMA_HOST, OLLAMA_TIMEOUT
from .options import OPTIONS


def generate(prompt: str, schema: dict, model: str) -> str:
    """Generate schema-constrained JSON with Ollama and return response text."""
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "format": schema,
        "stream": False,
        "think": False,
        "options": OPTIONS,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
    except requests.exceptions.Timeout as exc:
        raise requests.exceptions.Timeout(
            f"Ollama request timed out after {OLLAMA_TIMEOUT}s at {url}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise requests.exceptions.ConnectionError(
            f"Could not connect to Ollama at {url}: {exc}"
        ) from exc

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raw_body = getattr(response, "text", "")
        error_body = (
            raw_body[:2000].strip()
            if isinstance(raw_body, str)
            else ""
        )
        status = getattr(response, "status_code", None)

        if isinstance(status, int):
            details = error_body or str(exc) or "(empty response body)"
            message = f"Ollama returned HTTP {status}: {details}"
        else:
            # Handles mocks and responses without a usable status code.
            message = str(exc)

        raise requests.exceptions.HTTPError(
            message,
            response=response,
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise ValueError("Ollama returned invalid JSON") from exc

    if not isinstance(body, dict):
        raise ValueError("Ollama response was not a JSON object")

    if body.get("error"):
        raise RuntimeError(f"Ollama inference failed: {body['error']}")

    text = body.get("response", "")
    if not isinstance(text, str):
        raise ValueError("Ollama response did not contain text")
    if not text.strip():
        raise ValueError("Ollama returned an empty response")

    return text
