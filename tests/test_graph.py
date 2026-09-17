from langchain_core.messages import HumanMessage

from agente_seguranca.graph import _normalize_results, _source_fallback, route_query


def test_normalize_results_keeps_expected_source_fields():
    results = {"results": [{"title": "NR", "url": "https://example.com", "content": "Resumo"}]}

    assert _normalize_results(results) == [
        {"title": "NR", "url": "https://example.com", "content": "Resumo"}
    ]


def test_normalize_results_ignores_invalid_payload():
    assert _normalize_results({"results": [None, "texto", {"url": "https://example.com"}]}) == [
        {"title": "Fonte sem titulo", "url": "https://example.com", "content": ""}
    ]


def test_route_query_uses_sst_keyword_fallback(monkeypatch):
    class FakeResponse:
        content = "general"

    monkeypatch.setattr("agente_seguranca.graph._model", lambda: FakeModel(FakeResponse()))

    result = route_query(
        {
            "messages": [HumanMessage(content="Quais riscos de ergonomia existem?")],
            "route": "general",
            "sources": [],
        }
    )

    assert result == {"route": "technical"}


class FakeModel:
    def __init__(self, response):
        self.response = response

    def invoke(self, messages):
        return self.response


def test_source_fallback_returns_search_results():
    result = _source_fallback(
        "riscos ergonomicos",
        [{"title": "Fonte SST", "url": "https://example.com", "content": "Resumo"}],
    )

    assert "Fonte SST" in result
    assert "https://example.com" in result


def test_route_query_does_not_call_model_for_greeting(monkeypatch):
    def fail_model():
        raise AssertionError("saudacoes nao devem chamar o Gemini")

    monkeypatch.setattr("agente_seguranca.graph._model", fail_model)

    result = route_query(
        {
            "messages": [HumanMessage(content="Oi")],
            "route": "general",
            "sources": [],
        }
    )

    assert result == {"route": "general"}
