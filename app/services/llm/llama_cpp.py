
"""llama.cpp adapter using its OpenAI-compatible chat-completions endpoint."""

import json
import logging
import os
import time
from pathlib import Path

import requests

from app.core.config import LLAMA_CPP_HOST, LLAMA_CPP_TIMEOUT
from .options import OPTIONS

logger = logging.getLogger(__name__)


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

    schema_chars = len(json.dumps(schema))
    started = time.perf_counter()

    logger.info(
        "llama.cpp request started: model=%s host=%s "
        "prompt_chars=%d schema_chars=%d max_tokens=%s timeout=%ss",
        model,
        LLAMA_CPP_HOST,
        len(prompt),
        schema_chars,
        OPTIONS["num_predict"],
        LLAMA_CPP_TIMEOUT,
    )

    try:
        response = requests.post(
            f"{LLAMA_CPP_HOST}/v1/chat/completions",
            json=payload,
            timeout=LLAMA_CPP_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - started
        logger.exception(
            "llama.cpp request timed out after %.1fs "
            "(timeout=%ss, prompt_chars=%d, schema_chars=%d)",
            elapsed,
            LLAMA_CPP_TIMEOUT,
            len(prompt),
            schema_chars,
        )
        raise
    except requests.exceptions.RequestException:
        elapsed = time.perf_counter() - started
        logger.exception(
            "llama.cpp request failed after %.1fs",
            elapsed,
        )
        raise

    elapsed = time.perf_counter() - started
    logger.info(
        "llama.cpp HTTP response received in %.1fs: status=%s",
        elapsed,
        response.status_code,
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
            "model": model,
            "host": LLAMA_CPP_HOST,
            "elapsed_seconds": round(elapsed, 3),
            "prompt_chars": len(prompt),
            "schema_chars": schema_chars,
            "finish_reason": choice.get("finish_reason"),
            "usage": body.get("usage"),
            "response_length_chars": len(text),
            "response": text,
        }

        (output_dir / "llama_cpp_response_debug.json").write_text(
            json.dumps(diagnostic, indent=2),
            encoding="utf-8",
        )

    logger.info(
        "llama.cpp request completed in %.1fs: response_chars=%d",
        elapsed,
        len(text),
    )

    return text
