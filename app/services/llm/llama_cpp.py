
"""llama.cpp adapter using its OpenAI-compatible chat-completions endpoint."""

import json
import os
from pathlib import Path

import requests

from app.core.config import LLAMA_CPP_HOST, LLAMA_CPP_TIMEOUT
from .options import OPTIONS


def generate(prompt: str, schema: dict, model: str) -> str:
    """Generate schema-constrained JSON with a llama.cpp server."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": OPTIONS["temperature"],
        "seed": OPTIONS["seed"],
        "max_tokens": OPTIONS["num_predict"],
        "repeat_penalty": OPTIONS["repeat_penalty"],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "fireform_response",
                "strict": True,
                "schema": schema,
            },
        },
    }

    response = requests.post(
        f"{LLAMA_CPP_HOST}/v1/chat/completions",
        json=payload,
        timeout=LLAMA_CPP_TIMEOUT,
    )
    if not response.ok:
        raise requests.HTTPError(
            f"llama.cpp returned HTTP {response.status_code}: "
            f"{response.text[:3000]}",
            response=response,
        )

    response.raise_for_status()
    body = response.json()

    if not isinstance(body, dict):
        raise ValueError("llama.cpp response was not a JSON object")

    try:
        choice = body["choices"][0]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(
            "llama.cpp response did not contain message content"
        ) from exc

    if not isinstance(text, str) or not text.strip():
        raise ValueError("llama.cpp returned an empty response")

    diagnostic_dir = os.getenv("LLM_DIAGNOSTICS_DIR")
    if diagnostic_dir:
        output_dir = Path(diagnostic_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        diagnostic = {
            "finish_reason": choice.get("finish_reason"),
            "usage": body.get("usage"),
            "response_length_chars": len(text),
            "response": text,
        }
        (output_dir / "llama_cpp_response_debug.json").write_text(
            json.dumps(diagnostic, indent=2),
            encoding="utf-8",
        )

    return text
