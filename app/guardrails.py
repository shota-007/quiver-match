"""Safety layer around the agents: input screening, rate/budget limits, output validation."""

import re
import time
from collections import defaultdict, deque
from datetime import date

from .config import DAILY_TOKEN_BUDGET, RUNS_PER_CLIENT_PER_HOUR
from .models import BoardRecommendation, BoardSpec, DayPlan, SafetyAdvice

# ---------------------------------------------------------------- input screening

INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier)",
    r"disregard (all |the )?(instructions|rules)",
    r"system prompt|developer (message|mode)|jailbreak",
    r"you are now|act as|pretend (to be|you)",
    r"api[_ ]?key|portkey|password|\.env\b",
    r"<\s*script|javascript:",
    r"repeat (this|forever)|infinite|loop forever|call .* tool .* times",
]


def screen_text(field: str, text: str) -> str | None:
    """Return a refusal reason if free text looks like an attack, else None."""
    low = text.lower()
    for pat in INJECTION_PATTERNS:
        if re.search(pat, low):
            return f"The {field} field looks like an instruction to the AI rather than surf info, so it was blocked."
    return None


# ---------------------------------------------------------------- rate + budget


class Budget:
    """Per-client hourly run cap plus an app-wide daily token budget (in memory)."""

    def __init__(self) -> None:
        self.runs: dict[str, deque] = defaultdict(deque)
        self.day = date.today()
        self.tokens_today = 0

    def check(self, client_id: str) -> str | None:
        now = time.time()
        q = self.runs[client_id]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= RUNS_PER_CLIENT_PER_HOUR:
            return f"Rate limit: {RUNS_PER_CLIENT_PER_HOUR} recommendations per hour. Try again later."
        if self.day != date.today():
            self.day, self.tokens_today = date.today(), 0
        if self.tokens_today >= DAILY_TOKEN_BUDGET:
            return "The app has used its daily AI budget. Try again tomorrow."
        q.append(now)
        return None

    def spend(self, tokens: int) -> None:
        self.tokens_today += tokens


# ---------------------------------------------------------------- output validation

TOLERANCE = {"length_in": 1.0, "width_in": 0.25, "thickness_in": 0.125}
FIELDS = ("length_in", "width_in", "thickness_in", "volume_l", "tail", "fins", "rocker")


def _check_spec(label: str, spec: BoardSpec, calcs: list[dict]) -> tuple[BoardSpec, list[str]]:
    """Compare the agent's numbers to the calculator output for that board type.
    If they drifted (the model 'invented' dimensions), overwrite with the calculator's."""
    match = next((c for c in reversed(calcs) if c["board_type"] == spec.board_type), None)
    if match is None:
        return spec, [f"{label}: no calculator run for '{spec.board_type}', so these numbers are unverified."]
    issues = []
    for f, tol in TOLERANCE.items():
        if abs(getattr(spec, f) - match[f]) > tol:
            issues.append(f"{label} {f.replace('_in', '')}: agent said {getattr(spec, f)}, calculator says {match[f]}")
    if abs(spec.volume_l - match["volume_l"]) > 0.05 * match["volume_l"]:
        issues.append(f"{label} volume: agent said {spec.volume_l} L, calculator says {match['volume_l']} L")
    if issues:
        spec = BoardSpec(**{f: match[f] for f in FIELDS}, board_type=spec.board_type)
    return spec, issues


def _spec_from(calc: dict) -> BoardSpec:
    return BoardSpec(**{f: calc[f] for f in FIELDS}, board_type=calc["board_type"])


def validate_recommendation(rec: BoardRecommendation, calcs: list[dict], catalog_names: set[str],
                            allowed_types: list[str] | None = None, required_type: str | None = None,
                            recalc=None) -> tuple[BoardRecommendation, dict]:
    """Code checks on the Shaper's answer. `recalc(board_type)` runs the calculator for a type."""
    issues = []
    # 1. Board type: must match the surfer's style choice, and must be safe for their skill.
    want = required_type if required_type and rec.primary.board_type != required_type else None
    if not want and allowed_types and rec.primary.board_type not in allowed_types:
        want = "default"
    if want and recalc:
        calc = recalc(None if want == "default" else want)
        calcs.append(calc)
        issues.append(f"Primary type: agent said {rec.primary.board_type}, which "
                      + ("doesn't match the surfer's choice" if want != "default" else "isn't safe at this skill level")
                      + f"; replaced with {calc['board_type']}")
        rec.primary = _spec_from(calc)
    if rec.backup and allowed_types and rec.backup.board_type not in allowed_types:
        issues.append(f"Removed backup {rec.backup.board_type}: not safe at this skill level")
        rec.backup, rec.backup_when = None, ""
    # 2. Numbers: every dimension must match the calculator.
    primary, more = _check_spec("Primary", rec.primary, calcs)
    issues += more
    rec.primary = primary
    if rec.backup:
        rec.backup, more = _check_spec("Backup", rec.backup, calcs)
        issues += more
    invented = [m for m in rec.catalog_matches if m not in catalog_names]
    if invented:
        issues.append(f"Removed board models not in the catalog: {', '.join(invented)}")
        rec.catalog_matches = [m for m in rec.catalog_matches if m in catalog_names]
    return rec, {"passed": not issues, "corrections": issues}


def validate_plan(rec: BoardRecommendation, ranking: dict | None, assessments: list[dict]) -> tuple[BoardRecommendation, list[str]]:
    """Day-by-day board picks must come from code's ranking, and no-go days must be skipped."""
    issues = []
    ratings = {a["date"]: a["rating"] for a in assessments}
    days = {d["date"]: d for d in (ranking or {}).get("days", [])}
    owned = {b["name"] for b in (ranking or {}).get("boards", [])}
    by_date = {d.date: d for d in rec.days}
    fixed = []
    for dt in ratings:
        plan = by_date.get(dt) or DayPlan(date=dt, board="", why="")
        r = days.get(dt)
        want = r["pick"] if r else ("Skip" if ratings[dt] == "no-go" else "Rent")
        ok = plan.board == want
        if not ok and r and plan.board in owned:
            fits = {b["name"]: b["fit"] for b in r["ranked"]}
            ok = want not in ("Skip",) and want in fits and fits[plan.board] >= fits[want] - 5
        if ratings[dt] == "no-go" and plan.board != "Skip":
            ok = False
        if not ok:
            issues.append(f"{dt}: agent picked '{plan.board or 'nothing'}', code's pick is '{want}'")
            plan = DayPlan(date=dt, board=want, why=plan.why or "Code's pick for this day's forecast.")
        fixed.append(plan)
    rec.days = fixed
    picks = [d.board for d in fixed if d.board in owned]
    bring = [b for b in rec.bring if b in owned]
    for b in picks:
        if b not in bring:
            bring.append(b)
    if bring != rec.bring:
        issues.append(f"Packing list fixed to {bring or 'nothing'}")
    rec.bring = bring[:3]
    return rec, issues


def validate_safety(advice: SafetyAdvice | None, assessments: list[dict], safer: list[dict]) -> tuple[dict | None, list[str]]:
    """Safer spots and days must come from the tool's real ratings."""
    if advice is None:
        return None, []
    issues = []
    go = {(s["name"], d["date"]) for s in safer for d in s["days"] if d["rating"] == "go"}
    keep = [x for x in advice.safer_spots if (x.name, x.date) in go]
    if len(keep) != len(advice.safer_spots):
        issues.append("Removed safer-spot suggestions that were not rated 'go' by the forecast")
    ok_days = {a["date"] for a in assessments if a["rating"] != "no-go"}
    days = [d for d in advice.safer_days if d in ok_days]
    if len(days) != len(advice.safer_days):
        issues.append("Removed 'safer days' that are rated no-go")
    out = advice.model_dump()
    out.update({"safer_spots": [x.model_dump() for x in keep], "safer_days": days})
    return out, issues
