"""Plain-Python tools the agents call: spot lookup, live forecast, board calculator, catalog.

All board numbers come from `calc_board`, which is deterministic code, never from the model.
"""

import asyncio
import json
import math
import re
import time
from datetime import date, datetime, timedelta
from difflib import get_close_matches

import httpx

from .config import DATA_DIR, HTTP_TIMEOUT_S

SPOTS = json.loads((DATA_DIR / "spots.json").read_text())
CATALOG = json.loads((DATA_DIR / "boards.json").read_text())

M_TO_FT = 3.28084
CUBIC_IN_TO_L = 0.016387

# ---------------------------------------------------------------- spots


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower()).strip()


def lookup_spot(query: str) -> dict:
    """Find a spot in the curated database. Earliest-mentioned alias wins, so
    'El Porto near Manhattan Beach' resolves to El Porto, not the pier."""
    q = _norm(query)[:80]
    best = None
    for spot in SPOTS:
        for alias in [spot["name"].lower(), *spot["aliases"]]:
            m = re.search(rf"\b{re.escape(_norm(alias))}\b", q)
            idx = m.start() if m else -1
            if idx >= 0:
                key = (idx, -len(alias))
                if best is None or key < best[0]:
                    best = (key, spot)
    if best:
        return {"found": True, **best[1]}
    names = {a: s["name"] for s in SPOTS for a in [s["name"].lower(), *s["aliases"]]}
    close = get_close_matches(q, list(names), n=3, cutoff=0.85)
    if close:
        spot = next(s for s in SPOTS if s["name"] == names[close[0]])
        return {"found": True, "fuzzy_match_from": query, **spot}
    return {"found": False, "query": query, "known_spots": [s["name"] for s in SPOTS]}


async def geocode(client: httpx.AsyncClient, place: str) -> dict | None:
    r = await client.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": place[:80], "count": 1}, timeout=HTTP_TIMEOUT_S)
    hits = r.json().get("results") or []
    if not hits:
        return None
    h = hits[0]
    return {"name": h["name"], "region": ", ".join(x for x in [h.get("admin1"), h.get("country")] if x),
            "lat": h["latitude"], "lon": h["longitude"]}


# ---------------------------------------------------------------- forecast


def face_height_ft(hs_m: float, period_s: float) -> float:
    """Rough surfable face height from significant wave height and period.
    Long-period swell stands up taller at the beach than short wind chop."""
    if period_s < 8:
        factor = 0.7
    elif period_s < 12:
        factor = 1.0
    elif period_s < 15:
        factor = 1.3
    else:
        factor = 1.5
    return hs_m * M_TO_FT * factor


async def get_forecast(client: httpx.AsyncClient, lat: float, lon: float, start: date | None = None, days: int = 3) -> dict:
    """Daylight wave forecast for the trip dates from the free Open-Meteo Marine API (no key)."""
    start = start or date.today()
    r = await client.get(
        "https://marine-api.open-meteo.com/v1/marine",
        params={"latitude": lat, "longitude": lon, "timezone": "auto", "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=days - 1)).isoformat(),
                "hourly": "wave_height,wave_period,swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature"},
        timeout=HTTP_TIMEOUT_S,
    )
    if r.status_code != 200:
        return {"available": False, "reason": f"marine API returned {r.status_code}"}
    h = r.json().get("hourly", {})
    days: dict[str, list] = {}
    for i, t in enumerate(h.get("time", [])):
        hour = datetime.fromisoformat(t).hour
        hs, per = h["wave_height"][i], h["wave_period"][i]
        if hs is None or per is None or not 6 <= hour <= 18:
            continue
        sst = (h.get("sea_surface_temperature") or [None] * len(h["time"]))[i]
        days.setdefault(t[:10], []).append((face_height_ft(hs, per), per,
                                            h["swell_wave_direction"][i], h["swell_wave_period"][i], sst))
    if not days:
        return {"available": False, "reason": "no ocean data at this location"}
    out = []
    for day, rows in days.items():
        faces = [x[0] for x in rows]
        periods = [x[1] for x in rows]
        dirs = [x[2] for x in rows if x[2] is not None]
        temps = [x[4] for x in rows if x[4] is not None]
        out.append({
            "date": day,
            "face_ft_min": round(min(faces), 1),
            "face_ft_max": round(max(faces), 1),
            "avg_period_s": round(sum(periods) / len(periods), 1),
            "swell_dir_deg": round(sum(dirs) / len(dirs)) if dirs else None,
            "water_temp_c": round(sum(temps) / len(temps), 1) if temps else None,
        })
    return {"available": True, "source": "Open-Meteo Marine API", "days": out,
            "note": "face_ft is estimated from significant wave height x a period factor"}


# ---------------------------------------------------------------- board calculator

SKILL_FACTOR = {"beginner": 1.15, "novice": 0.85, "intermediate": 0.52, "advanced": 0.42, "expert": 0.37}
FITNESS_ADJ = {"low": 1.08, "average": 1.0, "high": 0.95}

# base width at 75 kg, width range, thickness range, planshape coefficient k, tail, fins, rocker
SHAPES = {
    "foam longboard":         (22.5, (21.5, 24.0), (3.0, 3.75), 0.75, "rounded square", "thruster (soft fins)", "low, flat rocker for easy paddling"),
    "longboard":              (22.75, (22.0, 24.0), (2.6, 3.25), 0.57, "square / rounded square", "single fin or 2+1", "low rocker for glide and trim"),
    "funboard":               (21.75, (20.75, 23.0), (2.6, 3.2), 0.60, "rounded square", "thruster", "moderate-low rocker"),
    "mid-length":             (21.25, (20.0, 22.5), (2.5, 3.0), 0.59, "rounded pin", "2+1 or single fin", "low-moderate rocker"),
    "fish":                   (21.0, (19.75, 22.5), (2.3, 2.9), 0.62, "swallow", "twin or quad", "flat rocker to keep speed in soft waves"),
    "groveler":               (20.25, (19.25, 21.5), (2.3, 2.8), 0.57, "squash or swallow", "quad or 5-fin", "flat entry rocker"),
    "hybrid shortboard":      (19.75, (18.75, 21.0), (2.3, 2.9), 0.545, "squash", "thruster or 5-fin", "moderate rocker"),
    "performance shortboard": (19.0, (18.0, 20.25), (2.2, 2.6), 0.52, "squash or rounded squash", "thruster", "moderate-to-high rocker"),
    "step-up":                (18.75, (18.0, 20.0), (2.3, 2.75), 0.51, "rounded pin", "thruster", "extra entry rocker for steep drops"),
}


# Board types that are safe and practical at each skill level (the backup board must come from here).
ALLOWED_TYPES = {
    "beginner": ["foam longboard", "funboard"],
    "novice": ["funboard", "longboard", "mid-length", "foam longboard"],
    "intermediate": ["fish", "hybrid shortboard", "mid-length", "groveler", "longboard", "funboard"],
    "advanced": ["performance shortboard", "groveler", "step-up", "fish", "hybrid shortboard", "mid-length", "funboard", "longboard"],
    "expert": ["performance shortboard", "groveler", "step-up", "fish", "hybrid shortboard", "mid-length", "funboard", "longboard"],
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def wave_adjustment(design_wave_ft: float, power: int) -> float:
    if design_wave_ft <= 2.5 or power <= 1:
        return 1.10          # small/weak: more volume to catch waves
    if design_wave_ft >= 7 or power >= 5:
        return 0.93          # big/powerful: less volume for control
    return 1.0


def choose_type(skill: str, design_wave_ft: float, power: int) -> str:
    if skill == "beginner":
        return "foam longboard"
    if skill == "novice":
        return "longboard" if design_wave_ft <= 2 and power <= 2 else "funboard"
    if skill == "intermediate":
        return "fish" if design_wave_ft < 3 or power <= 1 else "hybrid shortboard"
    if design_wave_ft < 3 or power <= 1:
        return "groveler"
    if design_wave_ft >= 6.5 or power >= 5:
        return "step-up"
    return "performance shortboard"


def base_length_in(board_type: str, height_in: float, weight_kg: float, skill: str) -> float:
    w = weight_kg
    rules = {
        "foam longboard": 96 if w <= 75 else 102 if w <= 90 else 108,
        "longboard": _clamp(108 + (w - 75) / 15 * 3, 108, 114),
        "funboard": _clamp(84 + (w - 50) * 0.35, 84, 102),
        "mid-length": _clamp(84 + (w - 60) * 0.25, 80, 96),
        "fish": _clamp(height_in - 4 + (w - 75) * 0.1, 62, 74),
        "groveler": _clamp(height_in - 3, 62, 74),
        "hybrid shortboard": _clamp(height_in + 1, 66, 78),
        "performance shortboard": _clamp(height_in - 1, 64, 78),
        "step-up": _clamp(height_in + 4, 70, 86),
    }
    return round(rules[board_type])


def calc_board(weight_kg: float, height_cm: float, skill: str, fitness: str,
               design_wave_ft: float, wave_power: int, board_type: str | None = None) -> dict:
    """Deterministic board sizing: target volume from weight x skill x fitness x waves,
    then length from the board type and the surfer's height, then width/thickness solved to hit it."""
    skill_f = SKILL_FACTOR[skill]
    fit_f = FITNESS_ADJ[fitness]
    wave_f = wave_adjustment(design_wave_ft, wave_power)
    if skill == "beginner":
        wave_f = max(wave_f, 1.0)       # never shrink a beginner's board
    target = weight_kg * skill_f * fit_f * wave_f
    btype = board_type or choose_type(skill, design_wave_ft, wave_power)
    base_w, (w_lo, w_hi), (t_lo, t_hi), k, tail, fins, rocker = SHAPES[btype]
    height_in = height_cm / 2.54

    length = base_length_in(btype, height_in, weight_kg, skill)
    width = _clamp(base_w + (weight_kg - 75) * 0.05, w_lo, w_hi)
    # Grow length up to 3" before thickening, then widen, roughly how a shaper adds volume.
    for _ in range(4):
        thick = target / (length * width * CUBIC_IN_TO_L * k)
        if thick <= t_hi:
            break
        length += 1
    thick = _clamp(thick, t_lo, t_hi)
    width = _clamp(target / (length * thick * CUBIC_IN_TO_L * k), w_lo, w_hi)
    width = round(width * 8) / 8
    thick = round(thick * 16) / 16
    volume = round(length * width * thick * CUBIC_IN_TO_L * k, 1)

    notes = []
    if not 0.92 <= volume / target <= 1.12:
        notes.append(f"A {btype} can't reach the {target:.1f} L target within normal dimensions; "
                     f"closest is {volume} L. Consider a different board type.")
    return {
        "board_type": btype,
        "length_in": length,
        "length_display": f"{int(length // 12)}'{int(length % 12)}\"",
        "width_in": width,
        "thickness_in": thick,
        "volume_l": volume,
        "tail": tail,
        "fins": fins,
        "rocker": rocker,
        "volume_math": (f"{weight_kg:.0f} kg x {skill_f} ({skill}) x {fit_f} (fitness {fitness}) "
                        f"x {wave_f} (waves {design_wave_ft:g} ft, power {wave_power}) = {target:.1f} L target"),
        "notes": notes,
    }


# ---------------------------------------------------------------- catalog


def search_catalog(board_type: str, rental_only: bool = False) -> list[dict]:
    hits = [b for b in CATALOG if b["type"] == board_type and (b["rental_common"] or not rental_only)]
    if not hits and board_type == "foam longboard":
        hits = [b for b in CATALOG if b["type"] == "funboard"]
    return hits[:4]



# ---------------------------------------------------------------- board styles (shortboard / funboard / longboard)

SHORTBOARD_TYPES = ("fish", "groveler", "hybrid shortboard", "performance shortboard", "step-up")
STYLE_OF = {**{t: "shortboard" for t in SHORTBOARD_TYPES}, "funboard": "funboard", "mid-length": "funboard",
            "longboard": "longboard", "foam longboard": "longboard"}


def style_to_type(style: str, skill: str, design_wave_ft: float, power: int) -> str:
    """Concrete board type for a style, before any safety check."""
    if style == "funboard":
        return "funboard"
    if style == "longboard":
        return "foam longboard" if skill == "beginner" else "longboard"
    if skill in ("advanced", "expert"):
        default = choose_type(skill, design_wave_ft, power)
        return default if default in SHORTBOARD_TYPES else "performance shortboard"
    return "hybrid shortboard"


def type_for_pref(pref: str, skill: str, design_wave_ft: float, power: int) -> tuple[str | None, str]:
    """The board type the surfer's style choice requires, or (None, reason) if it isn't safe for them."""
    if pref == "auto":
        return None, ""
    btype = style_to_type(pref, skill, design_wave_ft, power)
    if btype not in ALLOWED_TYPES[skill]:
        return None, (f"You picked a {pref}, but it isn't a safe choice for a {skill} surfer yet, "
                      "so we sized the best board for your level instead.")
    return btype, ""


def quiver(weight_kg: float, height_cm: float, skill: str, fitness: str, design_wave_ft: float, power: int,
           primary_type: str) -> list[dict]:
    """Shortboard, funboard and longboard sized for this surfer and these waves, each with a fit rating. Pure code."""
    best = STYLE_OF.get(primary_type)
    cards = []
    for style in ("shortboard", "funboard", "longboard"):
        btype = primary_type if style == best else style_to_type(style, skill, design_wave_ft, power)
        spec = calc_board(weight_kg, height_cm, skill, fitness, design_wave_ft, power, btype)
        if btype not in ALLOWED_TYPES[skill]:
            fit, note = "locked", "Not yet: build your skills on more foam first"
        elif style == best:
            fit, note = "best", "Best match for you and these waves"
        elif style == "longboard" and (design_wave_ft >= 6 or power >= 4):
            fit, note = "meh", "Hard to handle in powerful surf"
        elif style == "shortboard" and design_wave_ft < 2.5:
            fit, note = "meh", "Too little float for waves this small"
        elif style in ("longboard", "funboard") and design_wave_ft <= 3.5:
            fit, note = "good", "Great on small, soft days"
        else:
            fit, note = "good", "Solid alternative"
        cards.append({"style": style, "fit": fit, "fit_note": note,
                      **{k: spec[k] for k in ("board_type", "length_in", "length_display", "width_in", "thickness_in",
                                              "volume_l", "tail", "fins", "rocker")}})
    return cards


# ---------------------------------------------------------------- wetsuit + current board (pure code)

# Common wetsuit temperature guidance (approximate; people who run cold should go one step warmer).
WETSUIT_CHART = [
    (24, "Boardshorts or bikini", "Rash guard for sun"),
    (22, "Rash guard or 2 mm neoprene top", ""),
    (19, "3/2 mm springsuit or fullsuit", ""),
    (16, "3/2 mm fullsuit", "Booties optional"),
    (13, "4/3 mm fullsuit", "Booties recommended"),
    (10, "5/4 mm fullsuit", "Booties and a hood"),
    (-5, "6/5 mm hooded fullsuit", "Booties and gloves"),
]


def wetsuit(days: list[dict]) -> dict | None:
    temps = [d["water_temp_c"] for d in days if d.get("water_temp_c") is not None]
    if not temps:
        return None
    t = round(sum(temps) / len(temps), 1)
    suit, extras = next((s, e) for lo, s, e in WETSUIT_CHART if t >= lo)
    return {"temp_c": t, "temp_f": round(t * 9 / 5 + 32), "suit": suit, "extras": extras,
            "source": "Offshore model estimate (Open-Meteo); the beach can run a few degrees colder"}


# ---------------------------------------------------------------- trip safety (code decides, never the model)

SKILL_ORDER = ["beginner", "novice", "intermediate", "advanced", "expert"]
# Biggest comfortable face height (ft) and spot power (1-5) for each level. Above = caution; far above = no-go.
SKILL_LIMITS = {"beginner": (3, 2), "novice": (4, 3), "intermediate": (6, 4), "advanced": (10, 5), "expert": (99, 5)}


def assess_day(skill: str, spot: dict | None, day: dict) -> dict:
    max_ft, max_power = SKILL_LIMITS[skill]
    reasons, level = [], 0                      # 0 go, 1 caution, 2 no-go
    face = day.get("face_ft_max")
    if face is not None and face > max_ft:
        level = max(level, 2 if face > max_ft * 1.5 else 1)
        reasons.append(f"waves up to {face} ft (comfortable limit for a {skill}: {max_ft} ft)")
    if spot:
        power, floor = spot["power"], spot["skill_floor"]
        if power > max_power:
            level = max(level, 2 if power > max_power + 1 else 1)
            reasons.append(f"{spot['name']} is a power {power}/5 {spot['break_type']} over {spot['bottom']}")
        gap = SKILL_ORDER.index(floor) - SKILL_ORDER.index(skill)
        if gap > 0:
            level = max(level, 2 if gap >= 2 else 1)
            reasons.append(f"{spot['name']} suits {floor} surfers and up")
    return {"date": day["date"], "rating": ["go", "caution", "no-go"][level], "reasons": reasons,
            "face_ft_min": day.get("face_ft_min"), "face_ft_max": face, "avg_period_s": day.get("avg_period_s")}


def worst(assessments: list[dict]) -> str:
    order = ["go", "caution", "no-go"]
    return max((a["rating"] for a in assessments), key=order.index, default="go")


def _km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


async def find_safer_spots(client: httpx.AsyncClient, origin: dict, skill: str, start: date, days: int,
                           max_km: float = 120, limit: int = 3) -> list[dict]:
    """Nearby curated spots that suit this skill level, each with its own real forecast and day ratings."""
    _, max_power = SKILL_LIMITS[skill]
    cands = sorted((s for s in SPOTS if s["name"] != origin.get("name")
                    and SKILL_ORDER.index(s["skill_floor"]) <= SKILL_ORDER.index(skill) and s["power"] <= max_power
                    and _km(origin, s) <= max_km), key=lambda s: _km(origin, s))[:limit]
    out = []
    for s in cands:
        fc = await get_forecast(client, s["lat"], s["lon"], start, days)
        days_rated = [assess_day(skill, s, d) for d in fc.get("days", [])]
        out.append({"name": s["name"], "region": s["region"], "distance_km": round(_km(origin, s)),
                    "break_type": s["break_type"], "power": s["power"], "days": days_rated})
    return out


# ---------------------------------------------------------------- quiver meters (illustrative formula, explained in the UI)


def fit_dims(board_type: str, length_in: float, volume_l: float | None) -> dict:
    """Width/thickness for an owned board. If volume is missing, estimate it from typical proportions."""
    base_w, (w_lo, w_hi), (t_lo, t_hi), k = SHAPES[board_type][:4]
    if volume_l is None:
        width, thick = base_w, (t_lo + t_hi) / 2
        volume_l = round(length_in * width * thick * CUBIC_IN_TO_L * k, 1)
        estimated = True
    else:
        width = base_w
        thick = _clamp(volume_l / (length_in * width * CUBIC_IN_TO_L * k), t_lo, t_hi)
        width = _clamp(volume_l / (length_in * thick * CUBIC_IN_TO_L * k), w_lo, w_hi)
        estimated = False
    tail, fins, rocker = SHAPES[board_type][4:7]
    return {"width_in": round(width * 8) / 8, "thickness_in": round(thick * 16) / 16, "volume_l": volume_l,
            "volume_estimated": estimated, "tail": tail, "fins": fins, "rocker": rocker}


def board_meters(board: dict, ideal: dict, design_wave_ft: float, power: int, skill: str) -> dict:
    """Catching ease, control and turning (0-100) for one board on one day, plus a weighted fit score.
    r = board volume / ideal volume for this surfer and these waves; lx = how much longer than ideal."""
    r = board["volume_l"] / ideal["volume_l"]
    lx = (board["length_in"] - ideal["length_in"]) / ideal["length_in"]
    catch = 70 + 60 * (r - 1) + 30 * lx - (10 if design_wave_ft <= 2.5 and r < 1 else 0)
    # How "big" the day is (0 on small days, 1 at about 7.5 ft+ with real power): step-ups exist for these days.
    bigness = max(0.0, min(1.0, (design_wave_ft - 4.5) / 3)) * (1 if power >= 3 else 0.5)
    over = max(0.0, max(0, r - 1) + max(0, lx) - 0.15 * bigness)   # on big days a little extra board is normal
    control = 85 - 12 * power * over * (1.5 if design_wave_ft >= 6 else 1)
    if power >= 4:
        control += 10 if board["board_type"] in ("step-up", "performance shortboard") else -10 if board["board_type"] in (
            "fish", "groveler", "longboard", "foam longboard") else 0
    big = max(0, design_wave_ft - 3.5)                          # flat-rocker boards lose hold as waves get bigger
    if board["board_type"] in ("fish", "groveler"):
        control -= 7 * big
    elif board["board_type"] in ("hybrid shortboard", "performance shortboard", "step-up"):
        control += 3 * big
    # Big, powerful surf also punishes boards that are too SMALL: harder to paddle in early and to hold a line.
    under = max(0, 1 - r) + max(0, -lx)
    catch -= 120 * under * bigness
    control -= 150 * under * bigness
    turn = 95 - 0.9 * (board["length_in"] - 64) - 0.5 * max(0, board["volume_l"] - 30)
    if design_wave_ft <= 3 or power <= 2:
        w = [0.55, 0.15, 0.30]
    elif design_wave_ft >= 6 or power >= 4:
        w = [0.25, 0.55, 0.20]
    else:
        w = [0.40, 0.30, 0.30]
    if skill in ("beginner", "novice"):
        w = [w[0] + 0.15, w[1] + 0.05, w[2] - 0.20]
    m = [max(0, min(100, round(x))) for x in (catch, control, turn)]
    fit = round(sum(a * b for a, b in zip(w, m)))
    allowed = board["board_type"] in ALLOWED_TYPES[skill]
    if not allowed:
        fit = min(fit, 20)
    return {"catch": m[0], "control": m[1], "turn": m[2], "fit": fit, "weights": w, "allowed": allowed}


def board_label(b: dict) -> str:
    return b.get("name") or f"{int(b['length_in'] // 12)}'{int(round(b['length_in'] % 12))}\" {b['board_type']}"


def rank_quiver(weight_kg: float, height_cm: float, skill: str, fitness: str, quiver: list[dict],
                days: list[dict], power: int, assessments: list[dict]) -> dict:
    """For each trip day: the ideal board (calculator) and every owned board ranked by fit. Also a packing list."""
    boards = []
    for b in quiver:
        boards.append({**b, "name": board_label(b), **fit_dims(b["board_type"], b["length_in"], b.get("volume_l"))})
    ratings = {a["date"]: a["rating"] for a in assessments}
    per_day = []
    for d in days:
        design = round(((d["face_ft_min"] or 0) + (d["face_ft_max"] or 0)) / 2, 1) or 2.5
        ideal = calc_board(weight_kg, height_cm, skill, fitness, max(0.5, design), power)
        ranked = sorted(({"name": b["name"], "board_type": b["board_type"], "length_in": b["length_in"],
                          "volume_l": b["volume_l"], **board_meters(b, ideal, design, power, skill)} for b in boards),
                        key=lambda x: -x["fit"])
        best = ranked[0] if ranked else None
        per_day.append({"date": d["date"], "design_wave_ft": design, "rating": ratings.get(d["date"], "go"),
                        "ideal": {k: ideal[k] for k in ("board_type", "length_in", "length_display", "width_in", "thickness_in", "volume_l")},
                        "ideal_meters": board_meters({**ideal}, ideal, design, power, skill),
                        "ranked": ranked, "rent_needed": not best or best["fit"] < 55,
                        "pick": "Skip" if ratings.get(d["date"]) == "no-go" else (best["name"] if best and best["fit"] >= 55 else "Rent")})
    # packing: the board with the best total fit, plus a second if it wins any day by a clear margin
    totals = {}
    for d in per_day:
        for b in d["ranked"]:
            totals[b["name"]] = totals.get(b["name"], 0) + b["fit"]
    bring = [max(totals, key=totals.get)] if totals else []
    for d in per_day:
        if d["pick"] not in ("Skip", "Rent") and d["pick"] not in bring and len(bring) < 2:
            bring.append(d["pick"])
    return {"boards": boards, "days": per_day, "bring": bring}


# ---------------------------------------------------------------- local surf shops (OpenStreetMap, free, no key)

OSM_UA = {"User-Agent": "QuiverMatch/1.0 (https://github.com/shota-007; MGT 409 class project)"}


SHOPS_FILE = DATA_DIR / "spot_shops.json"


_NOMINATIM_LOCK = asyncio.Lock()
_nominatim_last = [0.0]


async def _nominatim(client: httpx.AsyncClient, q: str, viewbox: str) -> list | None:
    """One Nominatim (OpenStreetMap) search inside a box, paced to at most one request per second (their usage policy)."""
    async with _NOMINATIM_LOCK:
        wait = 1.1 - (time.monotonic() - _nominatim_last[0])
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await client.get("https://nominatim.openstreetmap.org/search", headers=OSM_UA, timeout=12,
                                 params={"q": q, "viewbox": viewbox, "bounded": 1, "format": "jsonv2", "limit": 40,
                                         "addressdetails": 1, "extratags": 1})
        except httpx.HTTPError:
            return None
        finally:
            _nominatim_last[0] = time.monotonic()
    return r.json() if r.status_code == 200 else None


async def fetch_shops_raw(client: httpx.AsyncClient, lat: float, lon: float, radius_km: float = 18) -> list[dict] | None:
    """Surf shops near a point from OpenStreetMap (Nominatim search, free, no key). None if the service didn't answer."""
    def box(rk: float) -> str:
        dlat, dlon = rk / 111, rk / (111 * max(0.2, math.cos(math.radians(lat))))
        return f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"

    found, answered = {}, False
    searches = [(radius_km, "surf"), (radius_km, "surfboards"), (radius_km, "surf shop"),
                (radius_km * 2, "surfboards"), (radius_km * 2, "surf")]
    for k, (rk, q) in enumerate(searches):
        if k >= 2 and len(found) >= 2:          # the first two searches always run; widen only if needed
            break
        res = await _nominatim(client, q, box(rk))
        if res is None:
            continue
        answered = True
        for x in res:
            name, kind = x.get("name") or "", (x.get("type") or "").lower()
            if x.get("category") != "shop" or not name or "wax" in name.lower() or not any(
                    w in kind for w in ("surf", "sport", "outdoor", "clothes", "boutique")):
                continue
            a, et = x.get("address") or {}, x.get("extratags") or {}
            addr = " ".join(v for v in (a.get("house_number"), a.get("road")) if v)
            city = a.get("city") or a.get("town") or a.get("village") or a.get("suburb") or ""
            text = " ".join([name, et.get("rental", ""), et.get("description", "")]).lower()
            found.setdefault((name, x.get("lat"), x.get("lon")), {"name": name, "lat": float(x["lat"]), "lon": float(x["lon"]), "shop": x.get("type", ""),
                                    "address": ", ".join(v for v in (addr, city) if v),
                                    "website": et.get("website") or et.get("contact:website") or "",
                                    "phone": et.get("phone") or et.get("contact:phone") or "",
                                    "rental_listed": "surf" in et.get("rental", "") or any(w in text for w in ("rental", "rent", "school", "lesson"))})
    return list(found.values()) if answered else None


def rank_shops(raw: list[dict], lat: float, lon: float, mode: str, limit: int = 2) -> dict:
    """Pick the best few shops for renting or buying: rental-tagged shops first for 'rent', board makers first for 'buy'."""
    shops = {}
    for s in raw:
        low = s["name"].lower().strip()
        if "fixme" in low or low in ("surfboards", "surf shop", "surf", "surfboard"):   # placeholder / generic names in OSM
            continue
        dist = _km({"lat": lat, "lon": lon}, s)
        score = (3 if mode == "rent" and s["rental_listed"] else 0) + (2 if mode == "buy" and "surfboard" in s["name"].lower() else 0) \
            + (1 if s["shop"] in ("surf", "water_sports") else 0) - dist / 10
        item = {**s, "distance_km": round(dist, 1), "score": round(score, 2)}
        if s["name"] not in shops or shops[s["name"]]["distance_km"] > item["distance_km"]:
            shops[s["name"]] = item
    term = "surfboard rental" if mode == "rent" else "surf shop"
    return {"mode": mode, "shops": sorted(shops.values(), key=lambda x: -x["score"])[:limit], "source": "OpenStreetMap contributors",
            "more_url": f"https://www.google.com/maps/search/{term.replace(' ', '+')}/@{lat},{lon},13z"}
