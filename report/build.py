"""Build report.html and slides.html from the app's real logs and test results.

    python -m eval.tokenomics --price-in X --price-cached Y --price-out Z   # refresh costs first
    python -m report.build

Every number comes from eval/results/*.json, logs/, or the app's data files. Items still missing
(prices, repo link, user trial) are shown as yellow TODO boxes and listed when the build finishes.
"""

import base64
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "report"
RESULTS = ROOT / "eval" / "results"

# ---------------------------------------------------------------- fill these in
AUTHOR = "S.K."
REPO_URL: str | None = "https://github.com/shota-007/quiver-match"
TRACE_RUN_ID = "c81763c946"   # beginner at Black's Beach: all three agents + a validator fix
BEGINNER_RUN_ID = "d8b41aeace"   # beginner who asked for a shortboard
# A real person trying the app (the rubric's Impact evidence). Fill with their actual words; leave None to hide.
USER_TRIAL: dict | None = {
    "who": "V M, a beginner (one of the three real surfers)",
    "quote": ("It was easy to follow because of the 1, 2 and 3 at the top even though I didn't really know the dimensions of my board. "
              "If Shota wasn't there in person and I wanted to surf I think this would be a great replacement. I saw the shops at the bottom "
              "where to rent and I would use it, I like how easy it is to follow despite being a beginner."),
    "short_quote": "If Shota wasn't there in person and I wanted to surf I think this would be a great replacement.",
    "before": "\"I have no idea how to do this since I'm a beginner and I probably wouldn't know what to do without it\" (needs a surfer friend)",
    "after": "a full plan in 17.5 s once the form was filled (run f99de77483 in the app's log)",
    "note": ("Their plan: El Porto rated caution all three days for a beginner, with Manhattan Beach Pier and Hermosa Beach Pier suggested as safer "
             "on the Monday, their own 8'0\" soft-top as the board, and Spyder Surfboards and Jack's Surfboards to rent from. The author, a surfer, "
             "watched the trial and agreed with the pick."),
    "screenshot": "report/img/user_trial.jpg",
}
# USER_TRIAL = {"who": "J.R., first-time surfer", "quote": "...", "before": "about 20 min asking a shop",
#               "after": "about 2 min with the app", "screenshot": "report/img/user_trial.jpg"}

TODOS: list[str] = []


def todo(label: str) -> str:
    TODOS.append(label)
    return f'<span class="todo">TO FILL: {html.escape(label)}</span>'


def img(name: str) -> str:
    path = REPORT_DIR / "img" / f"{name}.jpg"
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def money(x: float | None, label: str) -> str:
    if x is None:
        return todo(f"price for {label}")
    return f"${x:,.4f}" if x < 0.01 else f"${x:,.2f}"


def table(headers: list[str], rows: list[list], classes: list[list] | None = None) -> str:
    out = ["<table><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"]
    for i, row in enumerate(rows):
        cells = []
        for j, c in enumerate(row):
            cls = f' class="{classes[i][j]}"' if classes and classes[i][j] else ""
            cells.append(f"<td{cls}>{c}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    return "\n".join(out) + "</table>"


def fmt_int(x: float) -> str:
    return f"{x:,.0f}"


# ---------------------------------------------------------------- diagram


def diagram(n_spots: int = 54) -> str:
    def box(x, y, w, h, title, sub, fill="#ffffff", stroke="#ff6b4a", tc="#3b2618"):
        lines = "".join(f'<text x="{x + w / 2}" y="{y + 44 + 16 * k}" text-anchor="middle" font-size="11.5" fill="{tc}">{t}</text>'
                        for k, t in enumerate(sub))
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
                f'<text x="{x + w / 2}" y="{y + 24}" text-anchor="middle" font-size="14" font-weight="700" fill="{tc}">{title}</text>{lines}')
    arrow = lambda x1, y1, x2, y2: f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#5a2e14" stroke-width="2" marker-end="url(#arr)"/>'
    AG = ("#0f8a94", "#0b4f5c", "#ffffff")
    xs = [12, 152, 292, 432, 572, 712, 852]
    row = [("Surfer", ["body, skill", "quiver, spot", "trip dates"], ()), ("Guardrails", ["input checks", "injection screen", "rate + budget"], ()),
           ("Conditions", ["Agent", "ConditionsReport"], AG), ("Safety", ["code rates days", "Agent if risky"], AG),
           ("Shaper", ["Agent", "trip plan"], AG), ("Validator", ["picks, numbers,", "safer spots", "checked"], ()),
           ("Results", ["plan + 3D", "meters + render"], ())]
    parts = ['<svg viewBox="0 0 1000 330" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">',
             '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#5a2e14"/></marker></defs>',
             '<rect x="0" y="0" width="1000" height="330" rx="16" fill="#fff3e2"/>']
    for k, (x, (t, sub, style)) in enumerate(zip(xs, row)):
        parts.append(box(x, 30, 126, 100, t, sub, *style))
        if k:
            parts.append(arrow(xs[k - 1] + 126, 80, x - 2, 80))
    tools_ = [(292, ["lookup_spot", "get_forecast"]), (432, ["find_safer", "_spots"]), (572, ["rank_quiver", "calc_board", "search_catalog"])]
    for x, names in tools_:
        parts.append(arrow(x + 63, 130, x + 63, 178))
        parts.append(box(x, 180, 126, 30 + 16 * len(names), "tools", names))
    parts.append(box(12, 180, 266, 76, "Logs", ["runs.jsonl: tokens per agent", "traces/: every model + tool step"], "#ffffff", "#ff9a52"))
    parts.append(f'<text x="500" y="312" text-anchor="middle" font-size="12.5" fill="#8a6b55">Teal = AI agents (gpt-6-luna). White = code. '
                 f'Spot database: {n_spots} spots. Safety Agent runs only when a day is caution or no-go.</text></svg>')
    return "".join(parts)


def title_background() -> str:
    """The app's hero scene (sky, sun rays, barrel wave) as a 16:9 slide background."""
    page = (ROOT / "static" / "index.html").read_text()
    start = page.index('<svg class="scene"')
    inner = page[page.index(">", start) + 1:page.index("</svg>", start)]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 810" preserveAspectRatio="xMidYMax slice">'
           '<defs><linearGradient id="hi" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff8a5c"/>'
           '<stop offset="1" stop-color="#ff9e6d"/></linearGradient></defs>'
           '<rect width="1440" height="520" fill="url(#hi)"/>'
           f'<g transform="translate(0,510)">{inner}</g></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# ---------------------------------------------------------------- trace


def median_latency() -> str:
    """Median seconds per plan over every logged run of the shipped app (cache hits on repeated eval prompts would flatter the mean)."""
    runs = [json.loads(line) for line in (ROOT / "logs" / "runs.jsonl").read_text().splitlines() if line.strip()]
    vals = sorted(r["latency_s"] for r in runs if r.get("variant", "agent-low") == "agent-low" and r.get("source") != "safety-test" and r.get("latency_s"))
    return f"{vals[len(vals) // 2]:.1f}" if vals else "n/a"


def before_after_html(syn: dict, rs_file: Path) -> str:
    """Before/after the big-wave fix, for the personas and the real surfers (honest, data-driven)."""
    bdir = RESULTS / "before_fix"
    if not (bdir / "synthetic_personas_results.json").exists():
        return ""
    sb = json.loads((bdir / "synthetic_personas_results.json").read_text())
    rows = [["Synthetic personas: top pick", sb["summary"]["quiver_match_top1"], syn["summary"]["quiver_match_top1"]],
            ["Synthetic personas: top two", sb["summary"]["quiver_match_top2"], syn["summary"]["quiver_match_top2"]]]
    flips = []
    if rs_file.exists() and (bdir / "real_surfers_results.json").exists():
        rb, ra = json.loads((bdir / "real_surfers_results.json").read_text()), json.loads(rs_file.read_text())
        rows += [["Real surfers: top pick", rb["summary"]["quiver_match_top1"], ra["summary"]["quiver_match_top1"]],
                 ["Real surfers: top two", rb["summary"]["quiver_match_top2"], ra["summary"]["quiver_match_top2"]]]
        before = {(r["surfer"], r["date"]): r for r in rb["rows"]}
        for r in ra["rows"]:
            b = before.get((r["surfer"], r["date"]))
            if b and b["ours"] != r["ours"]:
                flips.append(f'{html.escape(r["who"])} on {r["date"]} ({html.escape(r["waves"].split(" (")[0])}): {html.escape(b["ours"])} → '
                             f'{html.escape(r["ours"])}; fit {b["fits"].get(b["ours"])}→{r["fits"].get(r["ours"])} (worked: {html.escape(r["actual"])})')
    sbefore = {(r["surfer"], r["date"]): r for r in sb["rows"]}
    fixed = sum(1 for r in syn["rows"] if sbefore.get((r["surfer"], r["date"]), {}).get("ours") != r["actual"] and r["ours"] == r["actual"])
    remaining = [r for r in syn["rows"] if r["ours"] != r["actual"]]
    return ('<p><b>What the stress test found, and the fix.</b> Before the fix, our formula missed every overhead day: it penalized boards that are too big '
            'for powerful surf but never boards that are too small, so it kept the regular shortboard instead of the step-up. We added two rules that only '
            'apply on big, powerful days: a board smaller or shorter than ideal loses catching ease and control (harder to paddle in early and to hold a line), '
            'and a step-up being up to 15% bigger than ideal is no longer penalized. The first version also applied the 15% allowance on small days, which '
            'broke three small/mid-day picks, so we limited it to big days before taking these numbers.</p>'
            + table(["Before → after the big-wave fix", "Before", "After"], rows)
            + f'<p class="small">The fix turned {fixed} persona misses into matches and changed nothing else there. It was designed after seeing these persona results, '
              'so the persona score is no longer an independent test; the real surfers are, and we did not tune on them. '
            + (("Real sessions whose pick changed: " + "; ".join(flips) + ". With so few real sessions, one flip is within noise; their liters are "
                "estimated from length, which the new rule is sensitive to.") if flips else "No real-surfer pick changed.")
            + f' Remaining persona misses: {len(remaining)}, all on small or punchy mid-size days where the formula prefers the more forgiving board.</p>')


def trace_table(trace: list[dict]) -> str:
    rows = []
    last_model = {}
    for i, s in enumerate(trace):
        if s["step"] == "model call":
            last_model[s["agent"]] = i
    for i, s in enumerate(trace):
        agent = {"conditions": "Conditions", "safety": "Safety"}.get(s["agent"], "Shaper")
        if s["step"] == "model call":
            what = "Model call"
            detail = ("Returns the typed " + {"Conditions": "ConditionsReport", "Safety": "SafetyAdvice"}.get(agent, "trip plan")
                      if last_model.get(s["agent"]) == i else "Decides which tool to call next")
            tok = f"{s['input_tokens']:,} in / {s['output_tokens']:,} out" + (
                f" ({s['cached_input_tokens']:,} cached)" if s.get("cached_input_tokens") else "")
        elif s["step"] == "tool call":
            args = s["args"] if isinstance(s["args"], str) else json.dumps(s["args"])
            what, detail, tok = f"Tool call: <code>{s['tool']}</code>", html.escape(args), ""
        else:
            what, detail, tok = f"Tool result: <code>{s['tool']}</code>", summarize_result(s["tool"], s["result"]), ""
        rows.append([str(len(rows) + 1), agent, what, detail, tok])
    return table(["#", "Agent", "Step", "Detail", "Tokens"], rows)


def summarize_result(tool: str, raw: str) -> str:
    try:
        r = json.loads(raw)
    except json.JSONDecodeError:
        return html.escape(raw[:160]) + "..."
    if tool == "lookup_spot" and r.get("found"):
        return f"Found {r['name']}: {r['break_type']}, {r['bottom']}, power {r['power']}/5, typical {r['typical_ft'][0]}-{r['typical_ft'][1]} ft, skill floor {r['skill_floor']}"
    if tool == "get_forecast" and r.get("available"):
        return "Live forecast: " + "; ".join(f"{d['date'][5:]} {d['face_ft_min']}-{d['face_ft_max']} ft @ {d['avg_period_s']} s" for d in r["days"])
    if tool == "calc_board" and "board_type" in r:
        return (f"{r['board_type']} {r['length_display']} x {r['width_in']:g}\" x {r['thickness_in']:g}\", {r['volume_l']} L "
                f"({html.escape(r['volume_math'].split('=')[-1].strip())})")
    if tool == "find_safer_spots" and isinstance(r, list):
        return "Safer spots: " + "; ".join(f"{x['name']} ({x['distance_km']} km): " + ", ".join(d["rating"] for d in x["days"]) for x in r)
    if tool == "rank_quiver" and isinstance(r, dict) and "days" in r:
        return "Per day: " + "; ".join(f"{d['date'][5:]} {d['rating']} pick {html.escape(d['pick'])}" for d in r["days"])
    if tool == "search_catalog" and isinstance(r, list):
        return "Models: " + ", ".join(html.escape(b["model"]) for b in r)
    return html.escape(json.dumps(r)[:160])


# ---------------------------------------------------------------- build


def main() -> None:
    tok = json.loads((RESULTS / "tokenomics.json").read_text())
    ev = json.loads((RESULTS / "eval_results.json").read_text())
    saf = json.loads((RESULTS / "safety_results.json").read_text())
    tr = json.loads((ROOT / "logs" / "traces" / f"{TRACE_RUN_ID}.json").read_text())
    spots = json.loads((ROOT / "app" / "data" / "spots.json").read_text())
    catalog = json.loads((ROOT / "app" / "data" / "boards.json").read_text())

    V = tok["variants"]
    low, med, base = V["agent-low"], V.get("agent-medium"), V.get("baseline")
    S = ev["summary"]
    prices = tok["prices_per_1m"]
    have_prices = None not in prices.values()
    scale = tok.get("scale", {})

    labels = {"agent-low": "Quiver Match (shipped: low effort)", "agent-medium": "Quiver Match at medium effort",
              "baseline": "Plain gpt-6-luna, no tools"}
    token_rows = [[labels.get(v, v), e["runs"], fmt_int(e["input"]["mean"]), fmt_int(e["cached_input"]["mean"]),
                   fmt_int(e["output"]["mean"]), f"{fmt_int(e['total']['mean'])} / {fmt_int(e['total']['p90'])}",
                   money(e["cost_per_run_usd"], "cost per run") if have_prices else todo("prices")]
                  for v, e in V.items()]
    token_table = table(["Variant", "Runs logged", "Input (mean)", "Cached input (mean)", "Output (mean)",
                         "Total (mean / p90)", "Cost per run"], token_rows)
    pa = low.get("per_agent_total_tokens", {})
    if pa:
        token_table += ('<p class="small">Per agent (shipped app, mean total tokens when the agent runs): '
                        + ", ".join(f"{k.title()} Agent {fmt_int(v['mean'])}" for k, v in pa.items()) + '.</p>')

    scale_rows = [[f"{int(u):,}", fmt_int(d["runs_per_month"]), fmt_int(d["tokens_per_month"]),
                   money(d["cost_per_month_usd"], f"{int(u):,} users") if have_prices else todo("prices"),
                   fmt_int(d["avg_tokens_per_day"])] for u, d in scale.items()]
    scale_table = table(["Active users", "Runs / month", "Tokens / month", "Cost / month", "Avg tokens / day"], scale_rows)
    budget_note = ""
    big = scale.get("10000", {})
    if big and not big.get("fits_daily_budget", True):
        budget_note = (f"At 10,000 users the app would average about {fmt_int(big['avg_tokens_per_day'])} tokens a day, more than its "
                       "current 2,000,000-token daily safety budget, so that limit would need raising (and moving to a database) at that scale.")

    def rate(key: str, v: str) -> str:
        val = S.get(key, {}).get(v, "n/a")
        return fmt_int(val) if isinstance(val, float) and val >= 100 else str(val)

    variants = [v for v in ("agent-low", "baseline") if v in S.get("ok", {})]
    metric_rows = [("Runs completed", "ok"), ("Board type suits skill + waves", "type_ok"), ("Volume in reference range", "volume_ok"),
                   ("Length given in wrong units", "length_unit_error"), ("Dimensions match stated volume (±15%)", "dims_consistent"),
                   ("Uses this week's live forecast", "uses_live_forecast"), ("Validator found nothing to fix", "validator_clean"),
                   ("Warns when spot is above skill", "skill_warning_ok"), ("Share of reasons citing a number", "reasons_with_numbers"),
                   ("Avg tokens per run", "tokens"), ("Avg output tokens", "output_tokens"), ("Avg latency (s)", "latency_s")]
    n_prof = len({r["profile"] for r in ev["rows"]})
    key_rows = ("type_ok", "volume_ok", "length_unit_error", "uses_live_forecast", "skill_warning_ok", "trip_flagged", "tokens")
    eval_table = table([f"Metric ({n_prof} trips)"] + [labels[v] for v in variants],
                       [[m] + [rate(k, v) for v in variants] for m, k in metric_rows if k in key_rows])
    effort_table = table([f"Quality check ({len({r['profile'] for r in ev['rows']})} trips)", "Low effort (shipped)", "Medium effort"],
                         [[m, rate(k, "agent-low"), rate(k, "agent-medium")] for m, k in metric_rows
                          if k in ("type_ok", "volume_ok", "validator_clean", "reasons_with_numbers", "output_tokens")]) if "agent-medium" in S.get("ok", {}) else ""

    rows_by = {(r["profile"], r["variant"]): r for r in ev["rows"] if r.get("ok")}
    ex = []
    for pid in ("P3", "P6", "P9"):
        for v in ("agent-low", "baseline"):
            r = rows_by.get((pid, v))
            if r:
                ex.append([f"{pid}: {html.escape(r['label'])}", labels[v], html.escape(r["board_type"]), r["dims"], r["volume_l"],
                           "yes" if r["type_ok"] and r["volume_ok"] else "no"])
    baseline_examples = table(["Profile", "Source", "Board type", "Dimensions as returned", "Volume (L)", "Type and volume ok"], ex)

    saf_rows = [[html.escape(r["category"]), html.escape(r["test"]), html.escape(r["attack"]),
                 "PASS" if r["passed"] else "FAIL", html.escape(r["evidence"][:85] + ("..." if len(r["evidence"]) > 85 else ""))] for r in saf["results"]]
    saf_classes = [["", "", "", "yes" if r["passed"] else "no", ""] for r in saf["results"]]
    safety_table = table(["Risk", "Defense tested", "Attack or malfunction", "Result", "Evidence (from the test)"], saf_rows, saf_classes)

    t = tr["usage"]["per_agent"]
    users_month = scale.get("1", {}).get("cost_per_month_usd")
    rs_file, rs_data = RESULTS / "real_surfers_results.json", ROOT / "eval" / "real_surfers.json"
    if rs_file.exists():
        rs = json.loads(rs_file.read_text()); sm = rs["summary"]
        surfers = json.loads(rs_data.read_text())["surfers"] if rs_data.exists() else []
        rs_top1, rs_top2, rs_n = sm["quiver_match_top1"], sm["quiver_match_top2"], str(sm["sessions"])
        rs_llm, rs_big = sm["plain_llm"], sm["biggest_board"]
        rs_rows = [[html.escape(r["surfer"]), r["date"], html.escape(r["spot"]), html.escape(r["waves"]), html.escape(r["actual"]),
                    html.escape(r["ours"]), html.escape(r.get("llm", "-"))] for r in rs["rows"]]
        rs_classes = [["", "", "", "", "", "yes" if r["ours"] == r["actual"] else "no", ("yes" if r.get("llm") == r["actual"] else "no") if r.get("llm") else ""]
                      for r in rs["rows"]]
        rs_block = (f'<p>{sm["surfers"]} real surfers (friends of the author) gave their profile, their quiver, and recent sessions with the board that actually worked best, '
                    'either through the app\'s <code>/survey</code> page or by text message, typed in by the author and flagged for review. '
                    f'{sm["scored_sessions"]} of {sm["sessions"]} sessions are scored (surfers with one board are excluded, because the pick is automatic). '
                    'For each session we rebuilt the conditions (their reported wave size, or the Open-Meteo record), ranked their own boards with the app\'s formula, '
                    'and compared our top pick with what worked. For comparison, a plain <code>gpt-6-luna</code> call (no tools) got the same information, and a naive rule always picks the biggest board.</p>'
                    + table(["Picker", "Matches the board that worked"], [["Quiver Match (top pick)", sm["quiver_match_top1"]], ["Quiver Match (top two)", sm["quiver_match_top2"]],
                                                                         ["Plain gpt-6-luna, no tools", sm["plain_llm"]], ["Always the biggest board", sm["biggest_board"]]])
                    + table(["Surfer", "Date", "Spot", "Waves", "Worked best", "Quiver Match", "Plain LLM"], rs_rows, rs_classes))
        rs_person = (f"{len(surfers)} real surfers shared their quivers and sessions for this project: "
                     + "; ".join(f"{html.escape(x.get('who', x['id']))} ({len(x['quiver'])} boards)" for x in surfers) + ". "
                     "Each one faces the same question before a session or trip: which of these boards, for these waves?") if surfers else ""
    else:
        rs_top1 = rs_top2 = rs_llm = rs_big = todo("real-surfer match rate")
        rs_n = "0"
        rs_block = ('<div class="todo-block"><b>TO FILL: real-surfer evidence.</b> Put 8-10 surfers in eval/real_surfers.json '
                    '(profile, quiver, recent sessions with the board that worked), run <code>python -m eval.real_surfers --llm</code>, then rebuild.</div>')
        TODOS.append("real surfers data (eval/real_surfers.json)")
        rs_person = todo("the surfers behind the evidence")
    syn_file = RESULTS / "synthetic_personas_results.json"
    if syn_file.exists():
        syn = json.loads(syn_file.read_text()); ss = syn["summary"]
        syn_rows = [[html.escape(r["surfer"]), html.escape(r["spot"]), html.escape(r["waves"].split(" (")[0]), html.escape(r["actual"]),
                     html.escape(r["ours"]), html.escape(r.get("llm", "-")), r["rating"]] for r in syn["rows"]]
        syn_classes = [["", "", "", "", "yes" if r["ours"] == r["actual"] else "no",
                        ("yes" if r.get("llm") == r["actual"] else "no") if r.get("llm") else "", ""] for r in syn["rows"]]
        misses = [r for r in syn["rows"] if r["ours"] != r["actual"]]
        syn_block = ('<div class="callout"><b>SYNTHETIC: not real people.</b> ' + html.escape(ss["label"]) + '</div>'
                     + table(["Picker", "Matches the rule-of-thumb board"],
                             [["Quiver Match (top pick)", ss["quiver_match_top1"]], ["Quiver Match (top two)", ss["quiver_match_top2"]],
                              ["Plain gpt-6-luna, no tools", ss["plain_llm"]], ["Always the biggest board", ss["biggest_board"]],
                              ["Safety: beginners flagged where expected", ss["safety_flags"]]])
                     + before_after_html(syn, rs_file)
                     + '<p class="small">Per-session persona results: <code>eval/results/synthetic_personas_results.json</code> in the repo.</p>')
        syn_ours, syn_llm = ss["quiver_match_top1"].split(" ")[0], ss["plain_llm"].split(" ")[0]
        bfile = RESULTS / "before_fix" / "synthetic_personas_results.json"
        syn_before = json.loads(bfile.read_text())["summary"]["quiver_match_top1"].split(" ")[0] if bfile.exists() else "n/a"
    else:
        syn_block, syn_ours, syn_llm, syn_before = "", "n/a", "n/a", "n/a"

    low_num = rate("reasons_with_numbers", "agent-low")
    med_num = rate("reasons_with_numbers", "agent-medium")
    values = {
        "AUTHOR": html.escape(AUTHOR),
        "REPO_LINK": f'<a href="{REPO_URL}">{REPO_URL}</a>' if REPO_URL else todo("GitHub repo link"),
        "REPO_CLONE": f"git clone {REPO_URL}.git" if REPO_URL else "",
        "N_SPOTS": str(len(spots)), "N_CA_SPOTS": str(sum(s["region"].endswith(", CA") for s in spots)),
        "N_CATALOG": str(len(catalog)),
        "DIAGRAM": diagram(len(spots)),
        "AVG_LATENCY": median_latency(),
        "AVG_TOKENS": fmt_int(low["total"]["mean"]), "N_LOW_RUNS": str(low["runs"]),
        "AVG_IN": fmt_int(low["input"]["mean"]), "AVG_CACHED": fmt_int(low["cached_input"]["mean"]),
        "AVG_OUT": fmt_int(low["output"]["mean"]),
        "CACHE_SHARE": f"{low['cached_input']['mean'] / low['input']['mean']:.0%}",
        "SAFETY_PASSED": f"{saf['passed']}/{saf['total']}",
        "RATIO": f"{low['total']['mean'] / base['total']['mean']:.0f}" if base else "n/a",
        "TRACE_RUN_ID": TRACE_RUN_ID, "TRACE_LATENCY": str(tr["latency_s"]),
        "TRACE_TOKENS": fmt_int(tr["usage"]["total"]["total_tokens"]),
        "TRACE_COND_TOKENS": fmt_int(t["conditions"]["total_tokens"]), "TRACE_SHAPER_TOKENS": fmt_int(t["shaper"]["total_tokens"]),
        "TRACE_SAFETY_TOKENS": fmt_int(t["safety"]["total_tokens"]) if "safety" in t else "0 (not needed)",
        "TRACE_TABLE": trace_table(tr["trace"]),
        "TOKEN_TABLE": token_table, "SCALE_TABLE": scale_table, "BUDGET_NOTE": budget_note,
        "PRICES": (f"${prices['input']}/1M input, ${prices['cached_input']}/1M cached input, ${prices['output']}/1M output tokens"
                   if have_prices else todo("gpt-6-luna prices per 1M tokens")),
        "COST_RUN": money(low["cost_per_run_usd"], "cost per run") if have_prices else todo("cost per run"),
        "COST_USER_MONTH": money(users_month, "per user") if have_prices else todo("cost per user per month"),
        "COST_100": money(scale.get("100", {}).get("cost_per_month_usd"), "100 users") if have_prices else todo("cost at 100 users"),
        "COST_10K": money(big.get("cost_per_month_usd"), "10,000 users") if have_prices else todo("cost at 10,000 users"),
        "RUNS_PER_MONTH": f"{tok['runs_per_user_per_month']:g}",
        "OUT_SAVING": f"{tok.get('reasoning_effort_output_saving', 0):.0%}",
        "MED_MORE_OUT": f"{med['output']['mean'] / low['output']['mean'] - 1:.0%}" if med else "n/a",
        "LOW_NUM": low_num, "MED_NUM": med_num,
        "FC_RAW": fmt_int(tok["forecast_payload"]["raw_tokens_est"]), "FC_SUM": fmt_int(tok["forecast_payload"]["summarized_tokens_est"]),
        "EFFORT_TABLE": effort_table, "EVAL_TABLE": eval_table, "BASELINE_EXAMPLES": baseline_examples,
        "SAFETY_TABLE": safety_table,
        "COND_SHARE": f"{pa['conditions']['mean'] / low['total']['mean']:.0%}" if pa else "a third",
        "SYN_BLOCK": syn_block, "SYN_OURS": syn_ours, "SYN_LLM": syn_llm, "SYN_BEFORE": syn_before, "RS_TOP1": rs_top1, "RS_TOP2": rs_top2, "RS_LLM": rs_llm, "RS_BIG": rs_big, "RS_N": rs_n, "RS_BLOCK": rs_block, "RS_PERSON": rs_person,
    }
    for key, per_variant in S.items():
        if isinstance(per_variant, dict) and key != "repeatability":
            for v, val in per_variant.items():
                values[f"EV_{key}_{v.replace('-', '_')}"] = str(val)

    values["TITLE_BG"] = title_background()
    if USER_TRIAL:
        u = USER_TRIAL
        shot = ""
        if u.get("screenshot") and (ROOT / u["screenshot"]).exists():
            data = base64.b64encode((ROOT / u["screenshot"]).read_bytes()).decode()
            shot = (f'<figure><img style="width:74%;margin:0 auto" src="data:image/jpeg;base64,{data}" alt="User trial"><figcaption>Figure 7. Screenshots from V M\'s own run: '
                    f'the beginner safety call with safer spots, and where to rent nearby with the run\'s token use and cost.</figcaption></figure>')
        values["USER_TRIAL_BLOCK"] = (f'<h3>A real user trying the app</h3><div class="callout"><b>{html.escape(u["who"])}</b>: '
                                      f'<i>"{html.escape(u["quote"])}"</i><br><b>Before:</b> {html.escape(u["before"])}<br>'
                                      f'<b>With Quiver Match:</b> {html.escape(u["after"])}<br>{html.escape(u.get("note", ""))}</div>' + shot)
        values["USER_QUOTE_SLIDE"] = (f'<p style="margin-top:12px;font-size:0.62em"><i>"{html.escape(u.get("short_quote", u["quote"]))}"</i>'
                                      f'<br><span class="small">V M, beginner, after using the app (plan in 17.5 s)</span></p>')
    else:
        values["USER_TRIAL_BLOCK"] = values["USER_QUOTE_SLIDE"] = ""
        print("Reminder: no real-user quote yet (USER_TRIAL in report/build.py). The Impact row is capped at half without it.")
    resp = tr["response"]
    beg = json.loads((ROOT / "logs" / "traces" / f"{BEGINNER_RUN_ID}.json").read_text())["response"]
    feet = lambda inches: f"{int(inches // 12)}'{int(round(inches % 12))}\""
    board_txt = lambda b: f"{feet(b['length_in'])} {b['board_type']} ({b['volume_l']} L)"
    p = tr["profile"]
    t_start = resp.get("trip", {}).get("start", "")
    tools_label = lambda b: b.get("name") or f"{feet(b['length_in'])} {b['board_type']}"
    total_in = round(p["height_cm"] / 2.54)
    days = resp.get("forecast_days", [])
    values.update({
        "TRACE_PROFILE": (f"a {p['skill']} surfer, {p['weight_kg'] / 0.453592:.0f} lb ({p['weight_kg']:.0f} kg), {total_in // 12}'{total_in % 12}\", "
                          f"{p['fitness']} fitness, {'renting' if p['intent'] == 'rent' else 'buying'} a board for {html.escape(resp['conditions']['spot_name'])}"
                          + f", {p.get('days', 1)} days from {p.get('start_date') or t_start}"
                          + (f", bringing {', '.join(html.escape(tools_label(b)) for b in p.get('quiver', []))}" if p.get("quiver") else "")),
        "TRACE_BOARD": board_txt(resp["recommendation"]["primary"]),
        "TRACE_SPOT": html.escape(resp["conditions"]["spot_name"]), "TRACE_POWER": str(resp["conditions"]["wave_power"]),
        "TRACE_FORECAST": (f"{min(d['face_ft_min'] for d in days)}-{max(d['face_ft_max'] for d in days)} ft" if days else "no forecast"),
        "BEG_BOARD": board_txt(beg["recommendation"]["primary"]),
        "N_LIVE": str(sum("(live)" in r["category"] for r in saf["results"])),
        "N_OFFLINE": str(sum("(live)" not in r["category"] for r in saf["results"])),
    })
    for path in sorted((REPORT_DIR / "img").glob("*.jpg")):
        values[f"IMG_{path.stem}"] = img(path.stem)

    for tmpl, out in (("report_template.html", "report.html"), ("slides_template.html", "slides.html")):
        src = REPORT_DIR / tmpl
        if not src.exists():
            continue
        text = re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], src.read_text())
        (ROOT / out).write_text(text)
        print(f"wrote {out} ({len(text) / 1e6:.2f} MB)")
    if TODOS:
        print("\nStill to fill in:")
        for item in dict.fromkeys(TODOS):
            print("  -", item)


if __name__ == "__main__":
    main()
