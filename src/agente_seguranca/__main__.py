"""Ponto de entrada: python -m agente_seguranca."""

import os

from dotenv import load_dotenv

from .ui import create_demo


def main() -> None:
    load_dotenv()
    missing = [name for name in ("GOOGLE_API_KEY", "TAVILY_API_KEY") if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Configure as variaveis obrigatorias: {names}")
    create_demo().launch()


if __name__ == "__main__":
    main()
