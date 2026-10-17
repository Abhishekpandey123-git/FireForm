"""Generation settings shared by inference providers."""

# Keep these values aligned with the existing FireForm/Ollama defaults.
OPTIONS = {
    "num_ctx": 8192,
    # Backstop for runaway generation; the largest real output (ICS 209) is ~8k tokens.
    "num_predict": 4096,
    "temperature": 0,
    "seed": 42,
    "repeat_penalty": 1.0,
    "repeat_last_n": 0,
}
