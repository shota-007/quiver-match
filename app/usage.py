"""Token accounting: per-agent usage, cost, and the run log used for tokenomics."""

import json
from datetime import datetime, timezone
from typing import Any

from .config import (LOG_DIR, PRICE_CACHED_INPUT_PER_M, PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M,
                     RUN_LOG, TRACE_DIR)


def usage_dict(result: Any) -> dict:
    u = result.usage() if callable(result.usage) else result.usage
    cached = getattr(u, "cache_read_tokens", 0) or 0
    return {
        "requests": u.requests,
        "tool_calls": getattr(u, "tool_calls", 0) or 0,
        "input_tokens": u.input_tokens,          # includes cached tokens
        "cached_input_tokens": cached,
        "output_tokens": u.output_tokens,
        "total_tokens": u.input_tokens + u.output_tokens,
    }


def cost_usd(u: dict) -> float | None:
    if None in (PRICE_INPUT_PER_M, PRICE_CACHED_INPUT_PER_M, PRICE_OUTPUT_PER_M):
        return None
    uncached = u["input_tokens"] - u["cached_input_tokens"]
    return round((uncached * PRICE_INPUT_PER_M + u["cached_input_tokens"] * PRICE_CACHED_INPUT_PER_M
                  + u["output_tokens"] * PRICE_OUTPUT_PER_M) / 1_000_000, 6)


def sum_usage(parts: list[dict]) -> dict:
    keys = ("requests", "tool_calls", "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
    return {k: sum(p.get(k, 0) for p in parts) for k in keys}


def trace_steps(agent_name: str, result: Any) -> list[dict]:
    """Flatten an agent run into readable steps: model calls, tool calls, tool results."""
    steps = []
    for msg in result.all_messages():
        usage = getattr(msg, "usage", None)
        if usage is not None and getattr(msg, "kind", "") == "response":
            steps.append({"agent": agent_name, "step": "model call",
                          "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                          "cached_input_tokens": getattr(usage, "cache_read_tokens", 0)})
        for part in msg.parts:
            kind = part.part_kind
            if kind == "tool-call" and part.tool_name != "final_result":
                steps.append({"agent": agent_name, "step": "tool call", "tool": part.tool_name, "args": part.args})
            elif kind == "tool-return" and part.tool_name != "final_result":
                steps.append({"agent": agent_name, "step": "tool result", "tool": part.tool_name,
                              "result": json.dumps(part.content, default=str)[:1500]})
    return steps


def write_run(record: dict, trace: list[dict], response: dict | None = None) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    TRACE_DIR.mkdir(exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    with RUN_LOG.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    (TRACE_DIR / f"{record['run_id']}.json").write_text(json.dumps({**record, "trace": trace, "response": response}, indent=2, default=str))
