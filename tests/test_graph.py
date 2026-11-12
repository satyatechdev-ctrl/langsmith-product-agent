"""Tests for the LangSmith-deployable graph factory."""

from __future__ import annotations

from product_agent.graph import make_graph
from product_agent.llm import DEFAULT_EURON_BASE_URL, DEFAULT_EURON_MODEL, get_euron_chat_model


def test_graph_factory_builds_without_making_model_requests(monkeypatch):
    monkeypatch.setenv("EURON_API_KEY", "test-key")
    monkeypatch.delenv("EURON_MODEL", raising=False)

    graph = make_graph()

    assert callable(graph.invoke)


def test_uses_euron_model_and_endpoint_by_default(monkeypatch):
    monkeypatch.setenv("EURON_API_KEY", "test-key")
    monkeypatch.delenv("EURON_MODEL", raising=False)
    monkeypatch.delenv("EURON_BASE_URL", raising=False)

    model = get_euron_chat_model()

    assert model.model_name == DEFAULT_EURON_MODEL
    assert model.openai_api_base == DEFAULT_EURON_BASE_URL


def test_requires_euron_api_key_without_openai_fallback(monkeypatch):
    monkeypatch.delenv("EURON_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-must-not-be-used")

    try:
        get_euron_chat_model()
    except ValueError as error:
        assert "EURON_API_KEY is required" in str(error)
    else:
        raise AssertionError("An Euron API key must be required.")
