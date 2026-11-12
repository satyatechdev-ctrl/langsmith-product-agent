"""Euron model configuration for the product agent."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

DEFAULT_EURON_MODEL = "euri-reasoning"
DEFAULT_EURON_BASE_URL = "https://api.euron.one/api/v1/euri"

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def get_euron_chat_model() -> ChatOpenAI:
    """Create the configured Euron chat model; fail clearly when its key is missing."""
    api_key = os.getenv("EURON_API_KEY")
    if not api_key:
        raise ValueError(
            "EURON_API_KEY is required. Set it in the environment or the project .env file."
        )

    return ChatOpenAI(
        model=os.getenv("EURON_MODEL", DEFAULT_EURON_MODEL),
        api_key=api_key,
        base_url=os.getenv("EURON_BASE_URL", DEFAULT_EURON_BASE_URL),
        temperature=0,
    )
