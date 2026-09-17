"""Interface web Gradio do agente."""

from __future__ import annotations

import gradio as gr

from .graph import ask_agent


DESCRIPTION = "Pesquise riscos, NRs, ergonomia e práticas de prevenção com fontes da web."


def respond(message: str, history: list[dict[str, str]]) -> str:
    del history
    if not message.strip():
        return "Escreva uma pergunta para começar."
    try:
        return ask_agent(message.strip())
    except Exception as error:
        error_text = str(error)
        if "503" in error_text or "UNAVAILABLE" in error_text:
            return (
                "O modelo Gemini está temporariamente indisponível por alta demanda. "
                "Aguarde alguns segundos e tente novamente."
            )
        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            return (
                "A cota gratuita da API Gemini foi atingida. "
                "Aguarde a renovação da cota ou configure um projeto com faturamento."
            )
        if "401" in error_text or "403" in error_text:
            return "A chave da API Gemini foi recusada. Confira GOOGLE_API_KEY no arquivo .env."
        return "Não foi possível concluir a consulta. Verifique o terminal do servidor para detalhes."


def create_demo() -> gr.ChatInterface:
    return gr.ChatInterface(
        fn=respond,
        title="Agente de Segurança do Trabalho",
        description=DESCRIPTION,
        examples=[
            "Quais os principais riscos ergonômicos na metalurgia?",
            "O que devo avaliar antes de uma atividade em espaço confinado?",
            "Qual a diferença entre EPI e EPC?",
        ],
        textbox=gr.Textbox(
            placeholder="Digite sua pergunta sobre segurança do trabalho...",
            label="Pergunta",
        ),
    )
