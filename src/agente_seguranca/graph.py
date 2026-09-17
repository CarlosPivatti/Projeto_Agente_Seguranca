"""Workflow LangGraph para o agente de seguranca do trabalho."""

from __future__ import annotations

import os
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Estado compartilhado entre os nos do workflow."""

    messages: Annotated[list[BaseMessage], add_messages]
    route: Literal["general", "technical"]
    sources: list[dict[str, str]]


ROUTER_PROMPT = """Classifique a mensagem do usuário em uma única categoria.

- technical: riscos ocupacionais, prevenção de acidentes, NRs brasileiras,
  EPI/EPC, higiene ocupacional, ergonomia, máquinas, incêndio, trabalho em
  altura, espaços confinados ou qualquer dúvida técnica de SST.
- general: saudações, despedidas e perguntas que não pedem orientação técnica.

Responda somente com technical ou general, sem explicações."""

ANSWER_PROMPT = """Você é um assistente de segurança do trabalho industrial.
Responda exclusivamente em português do Brasil, com linguagem clara e Markdown organizado.
Use somente as informações encontradas nas fontes e deixe explícito quando
houver incerteza. Cite as fontes no final com título e URL.

Sua resposta e educacional e nao substitui um profissional legalmente
habilitado, uma analise de risco, um PGR ou os procedimentos da empresa.
Nunca invente uma exigencia normativa."""

GENERAL_PROMPT = """Você é o assistente de um projeto de segurança do trabalho.
Responda exclusivamente em português do Brasil, de forma breve e cordial. Se a pessoa fizer
uma pergunta técnica, explique que pode pesquisar temas de SST, NRs, riscos,
EPI/EPC e ergonomia."""

TECHNICAL_KEYWORDS = (
    "metalurgia",
    "risco",
    "ergonomia",
    "quimica",
    "seguranca",
    "trabalho",
    "nr",
    "industrial",
    "doenca",
    "acidente",
    "fumos",
    "epi",
    "epc",
)

GREETING_WORDS = ("oi", "ola", "olá", "bom dia", "boa tarde", "boa noite")


def _model() -> ChatGoogleGenerativeAI:
    """Cria o modelo somente quando o workflow e iniciado."""
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        temperature=0.2,
    )


def _search_tool() -> TavilySearch:
    return TavilySearch(
        max_results=int(os.getenv("TAVILY_MAX_RESULTS", "5")),
        topic="general",
    )


def _latest_user_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def route_query(state: AgentState) -> dict[str, str]:
    """Classifica a intencao; mantem um fallback deterministico."""
    query = _latest_user_message(state).strip().casefold()
    if query in GREETING_WORDS:
        return {"route": "general"}
    has_technical_keyword = any(keyword in query for keyword in TECHNICAL_KEYWORDS)
    if has_technical_keyword:
        return {"route": "technical"}

    response = _model().invoke(
        [SystemMessage(content=ROUTER_PROMPT), HumanMessage(content=_latest_user_message(state))]
    )
    route = _response_text(response.content).strip().lower()
    if "technical" in route:
        return {"route": "technical"}
    return {"route": "general"}


def general_answer(state: AgentState) -> dict[str, list[BaseMessage]]:
    query = _latest_user_message(state).strip().casefold()
    if query in GREETING_WORDS:
        return {
            "messages": [
                HumanMessage(
                    content=(
                        "Olá! Sou o assistente de Segurança e Saúde no Trabalho. "
                        "Posso ajudar com NRs, riscos ocupacionais, ergonomia, EPI e EPC."
                    )
                )
            ]
        }
    response = _model().invoke(
        [SystemMessage(content=GENERAL_PROMPT), *_as_messages(state["messages"])]
    )
    return {"messages": [response]}


def technical_answer(state: AgentState) -> dict[str, list[BaseMessage] | list[dict[str, str]]]:
    query = _latest_user_message(state)
    results = _search_tool().invoke({"query": f"seguranca do trabalho Brasil {query}"})
    documents = _normalize_results(results)
    context = "\n\n".join(
        f"Fonte: {item['title']}\nURL: {item['url']}\nResumo: {item['content']}"
        for item in documents
    )
    try:
        response = _model().invoke(
            [
                SystemMessage(content=ANSWER_PROMPT),
                HumanMessage(content=f"Pergunta: {query}\n\nFontes pesquisadas:\n{context}"),
            ]
        )
    except Exception as error:
        if "429" not in str(error) and "RESOURCE_EXHAUSTED" not in str(error):
            raise
        response = HumanMessage(content=_source_fallback(query, documents))
    return {"messages": [response], "sources": documents}


def _source_fallback(query: str, documents: list[dict[str, str]]) -> str:
    """Entrega os resultados da busca quando o modelo excede a cota."""
    if not documents:
        return "Não encontrei fontes para esta consulta. Tente reformular a pergunta."
    lines = [
        "A cota do modelo de síntese foi atingida, mas estas fontes foram encontradas:",
        "",
        f"**Consulta:** {query}",
        "",
    ]
    for document in documents:
        lines.extend(
            [
                f"### {document['title']}",
                document["content"],
                f"Fonte: {document['url']}",
                "",
            ]
        )
    lines.append("Confira as fontes originais antes de tomar qualquer decisão operacional.")
    return "\n".join(lines)


def _as_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    return messages[-8:]


def _response_text(content: object) -> str:
    """Extrai texto de respostas Gemini antigas e em blocos multimodais."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            str(block["text"])
            for block in content
            if isinstance(block, dict) and block.get("text")
        ]
        if text_parts:
            return "".join(text_parts)
    return str(content)


def _normalize_results(results: object) -> list[dict[str, str]]:
    """Converte respostas da Tavily em um formato estavel para o prompt/UI."""
    if isinstance(results, dict):
        raw_results = results.get("results", [])
    else:
        raw_results = []
    documents: list[dict[str, str]] = []
    for result in raw_results:
        if not isinstance(result, dict):
            continue
        documents.append(
            {
                "title": str(result.get("title", "Fonte sem titulo")),
                "url": str(result.get("url", "")),
                "content": str(result.get("content", "")),
            }
        )
    return documents


def _route_condition(state: AgentState) -> str:
    return state.get("route", "general")


def build_graph():
    """Monta e compila o workflow do agente."""
    workflow = StateGraph(AgentState)
    workflow.add_node("router", route_query)
    workflow.add_node("general", general_answer)
    workflow.add_node("technical", technical_answer)
    workflow.add_edge(START, "router")
    workflow.add_conditional_edges(
        "router", _route_condition, {"general": "general", "technical": "technical"}
    )
    workflow.add_edge("general", END)
    workflow.add_edge("technical", END)
    return workflow.compile()


def ask_agent(question: str) -> str:
    """Executa uma pergunta e retorna somente o texto da resposta."""
    result = build_graph().invoke(
        {"messages": [HumanMessage(content=question)], "route": "general", "sources": []}
    )
    return _response_text(result["messages"][-1].content)
