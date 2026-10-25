"""Tokenomics from real logged runs: tokens per run, cost per run / user / month, and cost at scale.

    python -m eval.tokenomics --price-in 1.25 --price-cached 0.125 --price-out 10 [--runs-per-month 4]

Prices are USD per 1M tokens (defaults come from app/config.py). Reads logs/runs.jsonl, the
token usage the app records on every run, and writes eval/results/tokenomics.json and tokenomics.md.
"""

import argparse
import asyncio
import json
import statistics

import httpx

from app import tools
from app.config import (DAILY_TOKEN_BUDGET, PRICE_CACHED_INPUT_PER_M, PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M,
                        ROOT, RUN_LOG)

OUT_DIR = ROOT / "eval" / "results"
EL_PORTO = next(s for s in tools.SPOTS if s["name"] == "El Porto")


def load_runs() -> list[dict]:
    rows = [json.loads(line) for line in RUN_LOG.read_text().splitlines() if line.strip()]
    # Skip scripted safety-test runs (fake model, not real token usage).
    return [r for r in rows if r.get("source", "app") != "safety-test" and r.get("usage", {}).get("total")]


def stats(vals: list[float]) -> dict:
    vals = sorted(vals)
    return {"mean": round(statistics.mean(vals), 1), "median": round(statistics.median(vals), 1),
            "p90": round(vals[min(len(vals) - 1, int(0.9 * len(vals)))], 1), "min": vals[0], "max": vals[-1]}


def run_cost(inp: float, cached: float, out: float, p_in, p_cached, p_out) -> float | None:
    if None in (p_in, p_cached, p_out):
        return None
    return ((inp - cached) * p_in + cached * p_cached + out * p_out) / 1_000_000


async def forecast_payload_saving() -> dict:
    """Cost cut: the forecast tool sends 3 summarized daily rows instead of the raw hourly API response."""
    async with httpx.AsyncClient() as client:
        raw = await client.get("https://marine-api.open-meteo.com/v1/marine", timeout=10, params={
            "latitude": EL_PORTO["lat"], "longitude": EL_PORTO["lon"], "timezone": "auto", "forecast_days": 3,
            "hourly": "wave_height,wave_period,swell_wave_height,swell_wave_period,swell_wave_direction"})
        summary = await tools.get_forecast(client, EL_PORTO["lat"], EL_PORTO["lon"])
    raw_chars, sum_chars = len(raw.text), len(json.dumps(summary))
    return {"raw_hourly_chars": raw_chars, "summarized_chars": sum_chars,
            "raw_tokens_est": raw_chars // 4, "summarized_tokens_est": sum_chars // 4,
            "note": "Token counts estimated at ~4 characters per token."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-in", type=float, default=PRICE_INPUT_PER_M)
    ap.add_argument("--price-cached", type=float, default=PRICE_CACHED_INPUT_PER_M)
    ap.add_argument("--price-out", type=float, default=PRICE_OUTPUT_PER_M)
    ap.add_argument("--runs-per-month", type=float, default=4,
                    help="Assumed recommendations per active user per month")
    a = ap.parse_args()
    prices = (a.price_in, a.price_cached, a.price_out)

    runs = load_runs()
    by_variant: dict[str, list[dict]] = {}
    for r in runs:
        by_variant.setdefault(r.get("variant", "agent-low"), []).append(r)

    report = {"prices_per_1m": dict(zip(("input", "cached_input", "output"), prices)),
              "runs_per_user_per_month": a.runs_per_month, "variants": {}}
    md = ["| Variant | Runs | Input tok (mean) | Cached input (mean) | Output tok (mean) | Total (mean / p90) | Cost / run |",
          "|---|---|---|---|---|---|---|"]
    for v, rs in sorted(by_variant.items()):
        t = [r["usage"]["total"] for r in rs]
        inp = stats([x["input_tokens"] for x in t])
        cached = stats([x["cached_input_tokens"] for x in t])
        out = stats([x["output_tokens"] for x in t])
        tot = stats([x["total_tokens"] for x in t])
        cost = run_cost(inp["mean"], cached["mean"], out["mean"], *prices)
        entry = {"runs": len(rs), "input": inp, "cached_input": cached, "output": out, "total": tot,
                 "cost_per_run_usd": cost}
        per_agent = {}
        for agent in ("conditions", "safety", "shaper"):
            vals = [r["usage"]["per_agent"][agent]["total_tokens"] for r in rs if agent in r["usage"].get("per_agent", {})]
            if vals:
                per_agent[agent] = stats(vals)
        if per_agent:
            entry["per_agent_total_tokens"] = per_agent
        report["variants"][v] = entry
        md.append(f"| {v} | {len(rs)} | {inp['mean']:.0f} | {cached['mean']:.0f} | {out['mean']:.0f} | "
                  f"{tot['mean']:.0f} / {tot['p90']:.0f} | {'$%.5f' % cost if cost is not None else 'set prices'} |")

    shipped = report["variants"].get("agent-low")
    if shipped:
        tok = shipped["total"]["mean"]
        c = shipped["cost_per_run_usd"]
        scale = {}
        md += ["", f"**At scale (shipped app, agent-low, {a.runs_per_month:g} runs per user per month)**", "",
               "| Users | Runs / month | Tokens / month | Cost / month | Avg tokens / day* |", "|---|---|---|---|---|"]
        for users in (1, 100, 10_000):
            runs_m = users * a.runs_per_month
            per_day = runs_m / 30 * tok
            scale[users] = {"runs_per_month": runs_m, "tokens_per_month": round(runs_m * tok),
                            "cost_per_month_usd": round(runs_m * c, 4) if c is not None else None,
                            "avg_tokens_per_day": round(per_day), "fits_daily_budget": per_day <= DAILY_TOKEN_BUDGET}
            md.append(f"| {users:,} | {runs_m:,.0f} | {runs_m * tok:,.0f} | "
                      f"{('$%.2f' if runs_m * c >= 1 else '$%.4f') % (runs_m * c) if c is not None else 'set prices'} | {per_day:,.0f} |")
        md.append(f"\n*The app-wide daily budget is {DAILY_TOKEN_BUDGET:,} tokens; "
                  "raise it for 10,000 users." if scale[10_000]["avg_tokens_per_day"] > DAILY_TOKEN_BUDGET else "")
        report["scale"] = scale

    low, med = report["variants"].get("agent-low"), report["variants"].get("agent-medium")
    if low and med:
        saved = 1 - low["total"]["mean"] / med["total"]["mean"]
        report["reasoning_effort_saving"] = round(saved, 3)
        out_saved = 1 - low["output"]["mean"] / med["output"]["mean"]
        report["reasoning_effort_output_saving"] = round(out_saved, 3)
        md.append(f"\nLow vs. medium reasoning effort: low uses {saved:.0%} fewer total tokens per run "
                  f"({low['total']['mean']:.0f} vs. {med['total']['mean']:.0f}) and {out_saved:.0%} fewer output tokens "
                  f"({low['output']['mean']:.0f} vs. {med['output']['mean']:.0f}), the most expensive token type.")

    fc = asyncio.run(forecast_payload_saving())
    report["forecast_payload"] = fc
    md.append(f"\nForecast compaction: the raw hourly forecast is about {fc['raw_tokens_est']:,} tokens; "
              f"the summary the agent sees is about {fc['summarized_tokens_est']:,} tokens ({fc['note']})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "tokenomics.json").write_text(json.dumps(report, indent=2))
    (OUT_DIR / "tokenomics.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
