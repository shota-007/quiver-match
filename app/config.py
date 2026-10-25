"""Shared settings: paths, the one allowed model, token prices, and safety limits."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "app" / "data"
STATIC_DIR = ROOT / "static"
LOG_DIR = ROOT / "logs"
RUN_LOG = LOG_DIR / "runs.jsonl"
TRACE_DIR = LOG_DIR / "traces"

# The repo .env wins; the folder one level up is the fallback (how the teaching staff run it).
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# ---- Model: the course key allows only gpt-6-luna ----
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
# Portkey's gpt-6-luna supports function tools only on the Responses API.
MODEL_SETTINGS = OpenAIResponsesModelSettings(max_tokens=1500, openai_reasoning_effort="low")

# ---- Prices in USD per 1M tokens: gpt-6-luna published list price (OpenAI pricing page as reported by
# eesel.ai and anotherwrapper.com, October 2026). The course's Portkey key may be billed differently.
PRICE_INPUT_PER_M: float | None = 0.10
PRICE_CACHED_INPUT_PER_M: float | None = 0.01
PRICE_OUTPUT_PER_M: float | None = 0.50

# ---- Safety limits ----
CONDITIONS_LIMITS = UsageLimits(request_limit=5, tool_calls_limit=4, total_tokens_limit=25_000)
SHAPER_LIMITS = UsageLimits(request_limit=7, tool_calls_limit=7, total_tokens_limit=45_000)
SAFETY_LIMITS = UsageLimits(request_limit=3, tool_calls_limit=2, total_tokens_limit=15_000)
RUNS_PER_CLIENT_PER_HOUR = 15
DAILY_TOKEN_BUDGET = 2_000_000          # whole app, all users; stops runs once it is spent
HTTP_TIMEOUT_S = 8.0


def build_model() -> OpenAIResponsesModel:
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set (put it in .env here or one folder up).")
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(base_url=PORTKEY_BASE_URL, api_key=api_key))
