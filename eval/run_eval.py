"""10-profile evaluation: Quiver Match vs. a plain 'just ask the AI' baseline, plus a cost-cut check.

    python -m eval.run_eval                     # all variants (about 34 runs, ~250k tokens)
    python -m eval.run_eval --variants agent-low,baseline
    python -m eval.run_eval --rescore           # recompute checks on saved results, no model calls

Variants
  agent-low     the app as shipped (reasoning effort low)
  agent-medium  the app with reasoning effort medium (shows what the cost cut gives up, if anything)
  baseline      one gpt-6-luna call with no tools, no forecast, no calculator (like asking ChatGPT)
Plus a repeatability test: profile P6 run 3 times for agent-low and baseline.

Writes eval/results/eval_results.json and eval/results/eval_summary.md.
"""

import asyncio
import json
import re
import statistics
import sys
import time
import uuid

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from app import tools
from app.agents import recommend
from app.config import MODEL_SETTINGS, ROOT, build_model
from app.models import SurferProfile
from app.usage import cost_usd, usage_dict, write_run

EVAL_DIR = ROOT / "eval"
PROFILES = json.loads((EVAL_DIR / "profiles.json").read_text())["profiles"]
REPEAT_ID, REPEATS = "P6", 3
CONCURRENCY = 4
WARN_WORDS = re.compile(r"skill|experience|level|beginner|novice|advanced|expert|beyond|above|not suited|challenging|heavy", re.I)


# ---------------------------------------------------------------- baseline: one call, no tools


class BaselineAnswer(BaseModel):
    board_type: str
    length_in: float
    width_in: float
    thickness_in: float
    volume_l: float
    tail: str
    fins: str
    why: list[str]
    safety_notes: list[str] = Field(default_factory=list)


baseline_agent = Agent(
    build_model(), output_type=BaselineAnswer,
    model_settings=OpenAIResponsesModelSettings(max_tokens=MODEL_SETTINGS["max_tokens"], openai_reasoning_effort="low"),
    instructions="You are a knowledgeable surf coach. Recommend one surfboard with exact dimensions for this surfer and spot.",
)


async def run_baseline(p: SurferProfile) -> dict:
    t0 = time.perf_counter()
    res = await baseline_agent.run(
        f"I weigh {p.weight_kg:.0f} kg, I'm {p.height_cm:.0f} cm tall, my skill is {p.skill}, my paddle fitness is "
        f"{p.fitness}, and I surf {p.spot}. I want to {p.intent} a board. What board should I ride?")
    usage = {"total": usage_dict(res)}
    usage["cost_usd"] = cost_usd(usage["total"])
    run_id = uuid.uuid4().hex[:10]
    latency = round(time.perf_counter() - t0, 2)
    write_run({"run_id": run_id, "source": "eval", "variant": "baseline", "latency_s": latency,
               "profile": p.model_dump(), "usage": usage}, [])
    return {"ok": True, "run_id": run_id, "answer": res.output.model_dump(), "usage": usage, "latency_s": latency}


# ---------------------------------------------------------------- scoring


def implied_volume(btype: str, length: float, width: float, thick: float) -> float:
    """Volume implied by the stated dimensions, using the planshape coefficient for that board type."""
    key = next((k for k in tools.SHAPES if k in btype.lower()), None)
    if key is None:
        key = next((k for k in tools.SHAPES if k.split()[-1] in btype.lower()), None)
    k = tools.SHAPES[key][3] if key else 0.56
    return length * width * thick * tools.CUBIC_IN_TO_L * k


def normalize_length(length: float) -> tuple[float, bool]:
    """Plain-LLM answers often put feet'inches notation in an inches field (5.11 meaning 5'11").
    Convert those so the volume check is fair, and flag the unit error separately."""
    if length >= 15:
        return length, False
    feet, _, inches = f"{length:g}".partition(".")
    return int(feet) * 12 + (int(inches) if inches else 0), True


def dims_fields(btype: str, length: float, width: float, thick: float, volume: float) -> dict:
    length_in, unit_error = normalize_length(length)
    implied = implied_volume(btype, length_in, width, thick)
    return {"length_unit_error": unit_error, "dims_consistent": abs(implied - volume) / volume <= 0.15,
            "implied_volume_l": round(implied, 1)}


def score(profile: dict, variant: str, res: dict) -> dict:
    row = {"profile": profile["id"], "label": profile["label"], "variant": variant, "ok": res.get("ok", False)}
    if not row["ok"]:
        row["error"] = res.get("error", "")
        return row
    if variant == "baseline":
        a = res["answer"]
        board, why, notes, live = a, a["why"], a["safety_notes"], False
        validator_clean = None
    else:
        board = res["recommendation"]["primary"]
        why = res["recommendation"]["why"]
        notes = res["recommendation"]["safety_notes"] + res["conditions"]["hazards"]
        live = res["conditions"]["data_source"] == "live forecast"
        validator_clean = res["validation"]["passed"]
    lo, hi = profile["volume_range"]
    row.update({
        "board_type": board["board_type"],
        "dims": f"{board['length_in']:g} x {board['width_in']:g} x {board['thickness_in']:g}",
        "volume_l": board["volume_l"],
        "type_ok": any(t in board["board_type"].lower() for t in profile["ok_types"]),
        "volume_ok": lo <= board["volume_l"] <= hi,
        **dims_fields(board["board_type"], board["length_in"], board["width_in"], board["thickness_in"], board["volume_l"]),
        "uses_live_forecast": live,
        "validator_clean": validator_clean,
        "reasons_with_numbers": round(sum(bool(re.search(r"\d", w)) for w in why) / max(1, len(why)), 2),
        "skill_warning_ok": (any(WARN_WORDS.search(n) for n in notes) if profile["expect_skill_warning"] else None),
        "trip_flagged": ((res["trip"]["worst"] != "go") if variant != "baseline" and profile.get("expect_trip_flag") else None),
        "plan_days_ok": (len(res["recommendation"]["days"]) == len(res["trip"]["assessments"]) if variant != "baseline" else None),
        "tokens": res["usage"]["total"]["total_tokens"],
        "input_tokens": res["usage"]["total"]["input_tokens"],
        "cached_input_tokens": res["usage"]["total"]["cached_input_tokens"],
        "output_tokens": res["usage"]["total"]["output_tokens"],
        "latency_s": res["latency_s"],
    })
    return row


# ---------------------------------------------------------------- runner


async def run_one(sem: asyncio.Semaphore, profile: dict, variant: str) -> dict:
    p = SurferProfile(**{k: profile[k] for k in ("weight_kg", "height_cm", "skill", "fitness", "spot", "intent")},
                      quiver=[] if variant == "baseline" else profile.get("quiver", []))
    async with sem:
        try:
            if variant == "baseline":
                res = await run_baseline(p)
            else:
                res = await recommend(p, effort=variant.split("-")[1], source="eval")
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    row = score(profile, variant, res)
    print(f"  {row['variant']:<13} {row['profile']:<4} {'ok ' if row['ok'] else 'ERR'} "
          f"{row.get('board_type', row.get('error', ''))[:40]:<40} {row.get('volume_l', '')} L  {row.get('tokens', '')} tok", flush=True)
    return row


def rate(rows: list[dict], key: str) -> str:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return f"{sum(vals)}/{len(vals)}" if vals else "n/a"


def mean(rows: list[dict], key: str) -> float:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(statistics.mean(vals), 2) if vals else 0


def summarize(main_rows: list[dict], repeat_rows: list[dict]) -> tuple[dict, str]:
    summary, lines = {}, []
    lines.append("| Metric | " + " | ".join(sorted({r["variant"] for r in main_rows})) + " |")
    variants = sorted({r["variant"] for r in main_rows})
    lines.append("|---|" + "---|" * len(variants))
    metrics = [("Runs completed", "ok", rate), ("Board type suits skill + waves", "type_ok", rate),
               ("Volume in reference range", "volume_ok", rate), ("Length given in wrong units", "length_unit_error", rate),
               ("Dimensions match stated volume (±15%)", "dims_consistent", rate),
               ("Uses live forecast", "uses_live_forecast", rate), ("Validator found nothing to fix", "validator_clean", rate),
               ("Warns when spot is above skill", "skill_warning_ok", rate),
               ("Code flags risky trips (go/caution/no-go)", "trip_flagged", rate), ("Day-by-day plan complete", "plan_days_ok", rate),
               ("Share of reasons citing a number", "reasons_with_numbers", mean),
               ("Avg tokens per run", "tokens", mean), ("Avg input tokens", "input_tokens", mean),
               ("Avg cached input tokens", "cached_input_tokens", mean), ("Avg output tokens", "output_tokens", mean),
               ("Avg latency (s)", "latency_s", mean)]
    for label, key, fn in metrics:
        vals = {v: fn([r for r in main_rows if r["variant"] == v], key) for v in variants}
        summary[key] = vals
        lines.append(f"| {label} | " + " | ".join(str(vals[v]) for v in variants) + " |")

    lines.append(f"\n**Repeatability ({REPEAT_ID}, same input {REPEATS} times)**\n")
    lines.append("| Variant | Volumes (L) | Lengths (in) | Volume spread (max-min) |")
    lines.append("|---|---|---|---|")
    summary["repeatability"] = {}
    for v in sorted({r["variant"] for r in repeat_rows}):
        rs = [r for r in repeat_rows if r["variant"] == v and r["ok"]]
        vols = [r["volume_l"] for r in rs]
        lens = [float(r["dims"].split(" x ")[0]) for r in rs]
        spread = round(max(vols) - min(vols), 1) if vols else None
        summary["repeatability"][v] = {"volumes": vols, "lengths": lens, "spread_l": spread}
        lines.append(f"| {v} | {vols} | {lens} | {spread} |")
    lines.append("\nNote: repeat runs returned identical answers with identical token counts, which suggests the "
                 "gateway served cached responses for identical requests. Treat this as inconclusive about model variance.")
    return summary, "\n".join(lines)


async def main(variants: list[str]) -> None:
    sem = asyncio.Semaphore(CONCURRENCY)
    jobs = [run_one(sem, p, v) for v in variants for p in PROFILES]
    rep = next(p for p in PROFILES if p["id"] == REPEAT_ID)
    rep_variants = [v for v in ("agent-low", "baseline") if v in variants]
    rep_jobs = [run_one(sem, rep, v) for v in rep_variants for _ in range(REPEATS - 1)]
    print(f"Running {len(jobs) + len(rep_jobs)} runs...")
    t0 = time.perf_counter()
    rows = await asyncio.gather(*jobs, *rep_jobs)
    main_rows, extra = list(rows[:len(jobs)]), list(rows[len(jobs):])
    repeat_rows = [r for r in main_rows if r["profile"] == REPEAT_ID and r["variant"] in rep_variants] + extra
    write_outputs(main_rows, repeat_rows, round(time.perf_counter() - t0, 1))


def rescore() -> None:
    """Recompute the dimension checks on saved results (no new model calls)."""
    saved = json.loads((EVAL_DIR / "results" / "eval_results.json").read_text())
    for r in saved["rows"] + saved["repeat_rows"]:
        if r["ok"]:
            length, width, thick = (float(x) for x in r["dims"].split(" x "))
            r.update(dims_fields(r["board_type"], length, width, thick, r["volume_l"]))
    write_outputs(saved["rows"], saved["repeat_rows"], saved["wall_time_s"])


def write_outputs(main_rows: list[dict], repeat_rows: list[dict], wall_time_s: float) -> None:
    summary, md = summarize(main_rows, repeat_rows)
    out = {"profiles_source": json.loads((EVAL_DIR / "profiles.json").read_text())["_source"],
           "wall_time_s": wall_time_s, "summary": summary, "rows": main_rows, "repeat_rows": repeat_rows}
    (EVAL_DIR / "results" / "eval_results.json").write_text(json.dumps(out, indent=2))
    detail = ["\n**Per-profile results**\n", "| Profile | Variant | Board | Dims (in) | Volume (L) | Type ok | Volume ok | Dims consistent |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(main_rows, key=lambda r: (int(r["profile"][1:]), r["variant"])):
        if r["ok"]:
            detail.append(f"| {r['profile']} {r['label']} | {r['variant']} | {r['board_type']} | {r['dims']} | {r['volume_l']} "
                          f"| {r['type_ok']} | {r['volume_ok']} | {r['dims_consistent']} (implied {r['implied_volume_l']}) |")
        else:
            detail.append(f"| {r['profile']} | {r['variant']} | ERROR: {r['error'][:80]} | | | | | |")
    (EVAL_DIR / "results" / "eval_summary.md").write_text(md + "\n" + "\n".join(detail) + "\n")
    print("\n" + md)


if __name__ == "__main__":
    if "--rescore" in sys.argv:
        rescore()
        sys.exit()
    arg = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--variants=")), None)
    if "--variants" in sys.argv:
        arg = sys.argv[sys.argv.index("--variants") + 1]
    asyncio.run(main(arg.split(",") if arg else ["agent-low", "agent-medium", "baseline"]))
