"""FastAPI server: serves the page and the /api/recommend endpoint behind the guardrails."""

import json
import re
import time
import traceback
from datetime import date

import httpx

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import tools
from .agents import recommend
from .config import STATIC_DIR, TRACE_DIR
from .guardrails import Budget, screen_text
from .config import ROOT
from .models import SurferProfile, SurveyEntry

app = FastAPI(title="Quiver Match")
budget = Budget()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/spots")
def spots() -> list[dict]:
    keys = ("name", "region", "aliases", "break_type", "skill_floor", "power")
    return [{k: s[k] for k in keys} for s in tools.SPOTS]


@app.get("/api/replay/{run_id}")
def replay(run_id: str) -> JSONResponse:
    """Re-show a saved result (shareable link). The id is checked so it can't reach other files."""
    path = TRACE_DIR / f"{run_id}.json"
    if not re.fullmatch(r"[0-9a-f]{10}", run_id) or not path.exists():
        return JSONResponse({"ok": False, "error": "No saved result with that id."}, 404)
    saved = json.loads(path.read_text())
    if not saved.get("response"):
        return JSONResponse({"ok": False, "error": "That run has no saved result."}, 404)
    return JSONResponse({**saved["response"], "profile": saved["profile"]})


def _blocked(reason: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "blocked": True, "error": reason}, status_code=status)


@app.post("/api/recommend")
async def api_recommend(request: Request) -> JSONResponse:
    try:
        profile = SurferProfile(**await request.json())
    except (ValidationError, TypeError, ValueError) as e:
        msg = e.errors()[0]["msg"] if isinstance(e, ValidationError) else "Invalid request."
        return _blocked(f"Check your inputs: {msg}")
    for field_name in ("spot", "notes"):
        reason = screen_text(field_name, getattr(profile, field_name))
        if reason:
            return _blocked(reason)
    client_id = request.client.host if request.client else "unknown"
    reason = budget.check(client_id)
    if reason:
        return _blocked(reason, 429)
    try:
        result = await recommend(profile)
    except Exception as e:  # keep the UI alive on model/network failures
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": f"Something went wrong: {type(e).__name__}. Try again."}, 502)
    if result.get("ok"):
        budget.spend(result["usage"]["total"]["total_tokens"])
    return JSONResponse(result)


# ---------------------------------------------------------------- real-surfer survey (evidence collection)

SURVEY_FILE = ROOT / "eval" / "real_surfers.json"
LOCAL = {"127.0.0.1", "::1", "localhost", "testclient"}


def _load_survey() -> list[dict]:
    return json.loads(SURVEY_FILE.read_text())["surfers"] if SURVEY_FILE.exists() else []


def _save_survey(surfers: list[dict]) -> None:
    SURVEY_FILE.write_text(json.dumps({"surfers": surfers}, indent=1, default=str))


def _check_entry(entry: SurveyEntry) -> str | None:
    names = [tools.board_label(b.model_dump()) for b in entry.quiver]
    texts = [entry.who, entry.review_note] + [b.name for b in entry.quiver] + [x for s in entry.sessions for x in (s.spot, s.note)]
    for t in texts:
        if screen_text("survey", t):
            return "One of the text fields looks like an instruction to the AI rather than surf info."
    bad = [s.best_board for s in entry.sessions if s.best_board not in names]
    return f"'Best board' must be one of the surfer's own boards ({', '.join(names)}); got {bad[0]}" if bad else None


def _admin_only(request: Request) -> JSONResponse | None:
    host = request.client.host if request.client else ""
    return None if host in LOCAL else JSONResponse({"ok": False, "error": "Responses can only be managed on the author's computer."}, 403)


@app.get("/survey")
def survey_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "survey.html")


@app.post("/api/survey")
async def survey_submit(request: Request) -> JSONResponse:
    try:
        entry = SurveyEntry(**await request.json())
    except (ValidationError, TypeError, ValueError) as e:
        return _blocked("Check your inputs: " + (e.errors()[0]["msg"] if isinstance(e, ValidationError) else "invalid request"))
    reason = _check_entry(entry)
    if reason:
        return _blocked(reason)
    surfers = _load_survey()
    sid = f"S{max([int(x['id'][1:]) for x in surfers if x['id'][1:].isdigit()] or [0]) + 1}"
    surfers.append({"id": sid, **entry.model_dump(mode="json"), "source": "survey form"})
    _save_survey(surfers)
    return JSONResponse({"ok": True, "id": sid})


@app.get("/api/survey")
def survey_list(request: Request) -> JSONResponse:
    return _admin_only(request) or JSONResponse({"ok": True, "surfers": _load_survey()})


@app.put("/api/survey/{sid}")
async def survey_edit(sid: str, request: Request) -> JSONResponse:
    if (denied := _admin_only(request)):
        return denied
    try:
        entry = SurveyEntry(**await request.json())
    except (ValidationError, TypeError, ValueError) as e:
        return _blocked("Check your inputs: " + (e.errors()[0]["msg"] if isinstance(e, ValidationError) else "invalid request"))
    if (reason := _check_entry(entry)):
        return _blocked(reason)
    surfers = _load_survey()
    for k, x in enumerate(surfers):
        if x["id"] == sid:
            surfers[k] = {"id": sid, **entry.model_dump(mode="json"), "source": x.get("source", "survey form") + ", edited"}
            _save_survey(surfers)
            return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "Not found"}, 404)


@app.delete("/api/survey/{sid}")
def survey_delete(sid: str, request: Request) -> JSONResponse:
    if (denied := _admin_only(request)):
        return denied
    surfers = [x for x in _load_survey() if x["id"] != sid]
    _save_survey(surfers)
    return JSONResponse({"ok": True})


@app.post("/api/survey/evaluate")
async def survey_evaluate(request: Request) -> JSONResponse:
    if (denied := _admin_only(request)):
        return denied
    from eval.real_surfers import evaluate, write_results
    use_llm = (await request.json()).get("llm", False)
    surfers = _load_survey()
    if not surfers:
        return JSONResponse({"ok": False, "error": "No responses yet."}, 400)
    result = await evaluate(surfers, use_llm)
    write_results(result)
    return JSONResponse({"ok": True, **result})


# ---------------------------------------------------------------- spot photo + live preview (code only, no AI tokens)

PHOTOS = json.loads((ROOT / "app" / "data" / "spot_photos.json").read_text())
_preview_cache: dict[tuple, tuple[float, dict]] = {}


@app.get("/api/spot_photo")
def spot_photo(spot: str = "") -> JSONResponse:
    hit = tools.lookup_spot(spot[:80]) if spot else {"found": False}
    photo = PHOTOS.get(hit.get("name", "")) if hit.get("found") else None
    return JSONResponse({"spot": hit.get("name"), "is_default": photo is None, **(photo or PHOTOS["_default"])})


@app.get("/api/preview")
async def preview(spot: str, skill: str = "intermediate", start: str = "", days: int = 3) -> JSONResponse:
    if skill not in tools.SKILL_LIMITS or screen_text("spot", spot):
        return _blocked("Invalid preview request.")
    days = max(1, min(7, days))
    try:
        start_d = date.fromisoformat(start) if start else date.today()
    except ValueError:
        start_d = date.today()
    hit = tools.lookup_spot(spot[:80])
    if not hit.get("found"):
        return JSONResponse({"ok": False, "error": "Pick a spot from the list to see a live preview."})
    key = (hit["name"], skill, start_d.isoformat(), days)
    if key in _preview_cache and time.time() - _preview_cache[key][0] < 600:
        return JSONResponse(_preview_cache[key][1])
    async with httpx.AsyncClient() as client:
        fc = await tools.get_forecast(client, hit["lat"], hit["lon"], start_d, days)
    out = {"ok": True, "spot": hit["name"], "region": hit["region"], "break_type": hit["break_type"], "power": hit["power"],
           "days": [tools.assess_day(skill, hit, d) | {"water_temp_c": d.get("water_temp_c")} for d in fc.get("days", [])],
           "water": tools.wetsuit(fc.get("days", []))}
    _preview_cache[key] = (time.time(), out)
    return JSONResponse(out)


SHOPS = json.loads(tools.SHOPS_FILE.read_text()) if tools.SHOPS_FILE.exists() else {}


@app.get("/api/shops")
async def shops(spot: str, mode: str = "rent") -> JSONResponse:
    """Real surf shops near the break for renting or buying. Curated spots use a saved OpenStreetMap snapshot;
    other places try OpenStreetMap live. A Google Maps search link is always included as a fallback."""
    mode = "buy" if mode == "buy" else "rent"
    if screen_text("spot", spot):
        return _blocked("Invalid request.")
    hit = tools.lookup_spot(spot[:80])
    async with httpx.AsyncClient() as client:
        where = hit if hit.get("found") else await tools.geocode(client, spot[:80])
        if not where:
            return JSONResponse({"ok": False, "error": "Couldn't place that spot on the map."})
        raw = SHOPS.get(hit.get("name", "")) if hit.get("found") else None
        if raw is None:
            raw = await tools.fetch_shops_raw(client, where["lat"], where["lon"]) or []
    return JSONResponse({"ok": True, "spot": where.get("name", spot), **tools.rank_shops(raw, where["lat"], where["lon"], mode)})
