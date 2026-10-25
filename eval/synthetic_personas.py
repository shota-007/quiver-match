"""Stress test on SYNTHETIC personas (not real users): does the ranking follow common surf guidance, and does
the safety check flag beginners in the wrong water?

    python -m eval.synthetic_personas [--llm]

Writes eval/results/synthetic_personas_results.json. Reported separately from the real-surfer evidence.
"""

import asyncio
import json
import sys

from app.config import ROOT
from eval.real_surfers import evaluate

DATA = ROOT / "eval" / "synthetic_personas.json"
OUT = ROOT / "eval" / "results" / "synthetic_personas_results.json"


async def main(use_llm: bool) -> None:
    data = json.loads(DATA.read_text())
    result = await evaluate(data["surfers"], use_llm)
    flagged = [r for r in result["rows"] if r["expect_rating"]]
    ok = [r for r in flagged if r["rating"] != "go" and (r["expect_rating"] != "no-go" or r["rating"] == "no-go")]
    result["summary"]["safety_flags"] = f"{len(ok)}/{len(flagged)}"
    result["summary"]["label"] = data["_label"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result["summary"].items() if k != "label"}, indent=1))
    for r in result["rows"]:
        print(f"{r['surfer']:4} {r['spot'][:18]:18} {r['waves'][:22]:22} expected {r['actual']:16} ours {r['ours']:16} llm {r.get('llm', '-'):16} {r['rating']}")


if __name__ == "__main__":
    asyncio.run(main("--llm" in sys.argv))
