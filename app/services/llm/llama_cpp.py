"""llama.cpp adapter using its OpenAI-compatible chat-completions endpoint."""

import requests

from app.core.config import LLAMA_CPP_HOST, LLAMA_CPP_TIMEOUT
from .options import OPTIONS


def generate(prompt: str, schema: dict, model: str) -> str:
    """Generate schema-constrained JSON with a llama.cpp server.

    This targets modern llama.cpp builds that implement OpenAI-compatible
    ``/v1/chat/completions`` and JSON Schema response formats.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": OPTIONS["temperature"],
        "seed": OPTIONS["seed"],
        "max_tokens": OPTIONS["num_predict"],
        "repeat_penalty": OPTIONS["repeat_penalty"],
        # Match llama.cpp's documented response_format schema shape and the
        # benchmark adapter so both paths exercise equivalent constraints.
        "json_schema": schema,
    }
    response = requests.post(
        f"{LLAMA_CPP_HOST}/v1/chat/completions",
        json=payload,
        timeout=LLAMA_CPP_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("llama.cpp response was not a JSON object")
    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("llama.cpp response did not contain message content") from exc
    if not isinstance(text, str) or not text.strip():
        raise ValueError("llama.cpp returned an empty response")
    return text
