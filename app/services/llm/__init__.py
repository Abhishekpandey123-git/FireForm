"""Provider-agnostic language-model inference for FireForm.

The form-filling pipeline depends on this small interface rather than a specific
inference server. Ollama remains the default provider for backwards compatibility.
"""

from .factory import default_model, generate, normalize_provider

__all__ = ["default_model", "generate", "normalize_provider"]
