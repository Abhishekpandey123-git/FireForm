"""Unit tests for provider selection and HTTP adapters; no inference server required."""

from unittest.mock import Mock, patch

import pytest
import requests

from app.services.llm import factory, llama_cpp, ollama

SCHEMA = {
    "type": "object",
    "properties": {"incident_name": {"type": "string"}},
    "required": ["incident_name"],
    "additionalProperties": False,
}
PROMPT = "Extract incident fields."


def response_with_json(body):
    response = Mock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


def test_normalize_provider_accepts_supported_aliases():
    assert factory.normalize_provider("OLLAMA") == "ollama"
    assert factory.normalize_provider("llama-cpp") == "llama_cpp"
    assert factory.normalize_provider("llama.cpp") == "llama_cpp"
    assert factory.normalize_provider("llamacpp") == "llama_cpp"


def test_normalize_provider_rejects_unknown_provider():
    with pytest.raises(ValueError, match="expected 'ollama' or 'llama_cpp'"):
        factory.normalize_provider("unknown")


def test_default_model_is_provider_specific():
    assert factory.default_model("ollama") == factory.OLLAMA_MODEL
    assert factory.default_model("llama_cpp") == factory.LLAMA_CPP_MODEL


def test_ollama_payload_and_response_parsing():
    response = response_with_json({"response": '{"incident_name":"Test"}'})
    with patch.object(ollama.requests, "post", return_value=response) as post:
        result = ollama.generate(PROMPT, SCHEMA, "qwen-test")

    assert result == '{"incident_name":"Test"}'
    args, kwargs = post.call_args
    assert args[0].endswith("/api/generate")
    assert kwargs["json"]["model"] == "qwen-test"
    assert kwargs["json"]["format"] == SCHEMA
    assert kwargs["json"]["prompt"] == PROMPT
    assert kwargs["json"]["stream"] is False
    assert kwargs["timeout"] == ollama.OLLAMA_TIMEOUT


def test_ollama_raises_http_errors():
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("server error")
    with patch.object(ollama.requests, "post", return_value=response):
        with pytest.raises(requests.HTTPError, match="server error"):
            ollama.generate(PROMPT, SCHEMA, "qwen-test")


def test_ollama_rejects_malformed_response():
    with patch.object(ollama.requests, "post", return_value=response_with_json([])):
        with pytest.raises(ValueError, match="JSON object"):
            ollama.generate(PROMPT, SCHEMA, "qwen-test")


def test_llama_cpp_payload_and_response_parsing():
    response = response_with_json(
        {"choices": [{"message": {"content": '{"incident_name":"Test"}'}}]}
    )
    with patch.object(llama_cpp.requests, "post", return_value=response) as post:
        result = llama_cpp.generate(PROMPT, SCHEMA, "local-model")

    assert result == '{"incident_name":"Test"}'
    args, kwargs = post.call_args
    assert args[0].endswith("/v1/chat/completions")
    payload = kwargs["json"]
    assert payload["model"] == "local-model"
    assert payload["messages"] == [{"role": "user", "content": PROMPT}]
    assert payload["json_schema"] == SCHEMA
    assert "response_format" not in payload
    assert kwargs["timeout"] == llama_cpp.LLAMA_CPP_TIMEOUT


def test_llama_cpp_raises_http_errors():
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("server error")
    with patch.object(llama_cpp.requests, "post", return_value=response):
        with pytest.raises(requests.HTTPError, match="server error"):
            llama_cpp.generate(PROMPT, SCHEMA, "local-model")


def test_llama_cpp_rejects_missing_message_content():
    with patch.object(llama_cpp.requests, "post", return_value=response_with_json({"choices": []})):
        with pytest.raises(ValueError, match="did not contain message content"):
            llama_cpp.generate(PROMPT, SCHEMA, "local-model")


def test_factory_dispatches_to_selected_provider(monkeypatch):
    ollama_generate = Mock(return_value="ollama result")
    llama_generate = Mock(return_value="llama result")
    monkeypatch.setattr(factory, "LLM_PROVIDER", "ollama")
    with patch("app.services.llm.ollama.generate", ollama_generate):
        assert factory.generate(PROMPT, SCHEMA, "qwen-test") == "ollama result"
    ollama_generate.assert_called_once_with(PROMPT, SCHEMA, "qwen-test")

    monkeypatch.setattr(factory, "LLM_PROVIDER", "llama-cpp")
    with patch("app.services.llm.llama_cpp.generate", llama_generate):
        assert factory.generate(PROMPT, SCHEMA, "local-model") == "llama result"
    llama_generate.assert_called_once_with(PROMPT, SCHEMA, "local-model")
