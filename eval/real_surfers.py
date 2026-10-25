"""Real-surfer evidence: does Quiver Match pick the board that actually worked?

    python -m eval.real_surfers          # code ranking + "biggest board" baseline (0 AI tokens)
    python -m eval.real_surfers --llm    # also ask plain gpt-6-luna (no tools) for each session

Reads eval/real_surfers.json (see real_surfers.example.json). For each session we rebuild that day's
conditions (recorded wave size, or the Open-Meteo record if left blank), rank the surfer's own boards
with the app's formula, and compare the top pick with the board the surfer says worked best.
Writes eval/results/real_surfers_results.json and real_surfers.md.
"""

import asyncio
import json
import sys
from datetime import date

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from app import tools
from app.config import ROOT, build_model
from app.usage import usage_dict

DATA = ROOT / "eval" / "real_surfers.json"
OUT = ROOT / "eval" / "results"


class LLMPick(BaseModel):
    board: str


llm = Agent(build_model(), output_type=LLMPick,
            model_settings=OpenAIResponsesModelSettings(max_tokens=600, openai_reasoning_effort="low"),
            instructions="You are an experienced surf coach. Pick exactly one board from the surfer's quiver for this session. "
                         "Answer with the board's name exactly as written.")


async def session_day(client: httpx.AsyncClient, spot: dict | None, s: dict) -> dict:
    if s.get("face_ft") is not None:
        f = float(s["face_ft"])
        return {"date": s["date"], "face_ft_min": round(f * 0.8, 1), "face_ft_max": f, "avg_period_s": s.get("period_s") or 10,
                "source": "surfer's report"}
    if spot:
        fc = await tools.get_forecast(client, spot["lat"], spot["lon"], date.fromisoformat(s["date"]), 1)
        if fc.get("days"):
            return {**fc["days"][0], "source": "Open-Meteo record"}
    return {"date": s["date"], "face_ft_min": 2, "face_ft_max": 3, "avg_period_s": 10, "source": "unknown (default 2-3 ft)"}


async def evaluate(surfers: list[dict], use_llm: bool = False) -> dict:
    """Score every session: our top pick vs. the board that worked (plus optional plain-LLM and biggest-board baselines)."""
    rows, tokens = [], 0
    async with httpx.AsyncClient() as client:
        for sf in surfers:
            names = [tools.board_label(b) for b in sf["quiver"]]
            for s in sf["sessions"]:
                spot = tools.lookup_spot(s["spot"])
                spot = spot if spot.get("found") else None
                day = await session_day(client, spot, s)
                power = spot["power"] if spot else 3
                assess = [tools.assess_day(sf["skill"], spot, day)]
                r = tools.rank_quiver(sf["weight_kg"], sf["height_cm"], sf["skill"], sf.get("fitness", "average"),
                                      sf["quiver"], [day], power, assess)
                ranked = [b["name"] for b in r["days"][0]["ranked"]]
                biggest = max(r["boards"], key=lambda b: b["volume_l"])["name"]
                row = {"surfer": sf["id"], "who": sf.get("who", ""), "date": s["date"], "spot": s["spot"],
                       "waves": f"{day['face_ft_min']}-{day['face_ft_max']} ft @ {day['avg_period_s']}s ({day['source']})",
                       "actual": s["best_board"], "ours": ranked[0], "ours_top2": ranked[:2], "biggest": biggest,
                       "quiver_size": len(sf["quiver"]), "fits": {b["name"]: b["fit"] for b in r["days"][0]["ranked"]},
                       "rating": assess[0]["rating"], "expect_rating": s.get("expect_rating")}
                if use_llm:
                    res = await llm.run(
                        f"Surfer: {sf['weight_kg']} kg, {sf['height_cm']} cm, {sf['skill']}, fitness {sf.get('fitness', 'average')}.\n"
                        f"Spot: {s['spot']}. Conditions: {row['waves']}.\nQuiver: " + "; ".join(
                            f"{n} ({b['board_type']}, {b['length_in']} in, {b.get('volume_l') or '?'} L)" for n, b in zip(names, sf["quiver"])))
                    row["llm"] = res.output.board.strip()
                    tokens += usage_dict(res)["total_tokens"]
                rows.append(row)

    # Sessions where the surfer owns a single board say nothing about picking, so they are excluded from the rates.
    scored = [r for r in rows if r["quiver_size"] > 1]

    def rate(fn):
        hits = [fn(r) for r in scored]
        return f"{sum(hits)}/{len(hits)} ({100 * sum(hits) / len(hits):.0f}%)" if hits else "n/a"

    summary = {"sessions": len(rows), "scored_sessions": len(scored), "surfers": len(surfers),
               "quiver_match_top1": rate(lambda r: r["ours"] == r["actual"]),
               "quiver_match_top2": rate(lambda r: r["actual"] in r["ours_top2"]),
               "biggest_board": rate(lambda r: r["biggest"] == r["actual"]),
               "plain_llm": rate(lambda r: r.get("llm") == r["actual"]) if use_llm else "not run", "llm_tokens": tokens}
    return {"summary": summary, "rows": rows}


def write_results(result: dict) -> str:
    sm, rows = result["summary"], result["rows"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "real_surfers_results.json").write_text(json.dumps(result, indent=2))
    md = [f"Scored sessions: {sm['scored_sessions']} of {sm['sessions']} (surfers with 2+ boards)", "",
          "| Picker | Matches the board that worked |", "|---|---|",
          f"| Quiver Match (top pick) | {sm['quiver_match_top1']} |", f"| Quiver Match (top 2) | {sm['quiver_match_top2']} |",
          f"| Plain gpt-6-luna, no tools | {sm['plain_llm']} |", f"| Always the biggest board | {sm['biggest_board']} |",
          "", "| Surfer | Date | Spot | Waves | Worked best | Quiver Match | Plain LLM |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['surfer']} | {r['date']} | {r['spot']} | {r['waves']} | {r['actual']} | {r['ours']} | {r.get('llm', '-')} |" for r in rows]
    (OUT / "real_surfers.md").write_text("\n".join(md) + "\n")
    return "\n".join(md)


async def main(use_llm: bool) -> None:
    if not DATA.exists():
        sys.exit(f"Create {DATA.relative_to(ROOT)} first (use the /survey page or copy real_surfers.example.json).")
    surfers = json.loads(DATA.read_text())["surfers"]
    print(write_results(await evaluate(surfers, use_llm)))


if __name__ == "__main__":
    asyncio.run(main("--llm" in sys.argv))
