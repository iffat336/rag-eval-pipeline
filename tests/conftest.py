import os

# Unit tests mock the LLM/embedding clients and never hit the network, but
# src.config reads OPENAI_API_KEY at import time to fail fast in real runs.
# Provide a dummy value so test collection doesn't require real credentials.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-unit-tests")
