"""Typed inputs and outputs passed between the UI, the agents, and the validator."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Skill = Literal["beginner", "novice", "intermediate", "advanced", "expert"]
Fitness = Literal["low", "average", "high"]
BoardPref = Literal["auto", "shortboard", "funboard", "longboard"]
BoardType = Literal[
    "foam longboard", "longboard", "funboard", "mid-length", "fish",
    "groveler", "hybrid shortboard", "performance shortboard", "step-up",
]


class QuiverBoard(BaseModel):
    name: str = Field(default="", max_length=40)
    board_type: BoardType
    length_in: float = Field(ge=48, le=144)
    volume_l: float | None = Field(default=None, ge=10, le=160)


class SurferProfile(BaseModel):
    weight_kg: float = Field(ge=25, le=180)
    height_cm: float = Field(ge=120, le=220)
    skill: Skill
    fitness: Fitness = "average"
    spot: str = Field(min_length=2, max_length=80)
    intent: Literal["rent", "buy"] = "buy"
    board_pref: BoardPref = "auto"
    notes: str = Field(default="", max_length=300)
    quiver: list[QuiverBoard] = Field(default_factory=list, max_length=6, description="Boards the surfer owns")
    start_date: date | None = Field(default=None, description="Trip start; default today")
    days: int = Field(default=3, ge=1, le=7)


class ConditionsReport(BaseModel):
    spot_name: str
    in_spot_database: bool = Field(description="True only if lookup_spot found the spot in the curated database")
    break_type: str
    bottom: str
    wave_power: int = Field(ge=1, le=5, description="1 = soft and rolling, 5 = heavy and hollow")
    forecast_summary: str = Field(description="1-2 sentences built only from get_forecast numbers, or 'forecast unavailable'")
    forecast_range_ft: list[float] = Field(description="[min, max] wave face height in ft over the forecast window, or the spot's typical range")
    design_wave_ft: float = Field(ge=0.5, le=20, description="Representative wave height the board should be designed for")
    skill_floor: str
    hazards: list[str] = Field(default_factory=list)
    data_source: Literal["live forecast", "spot typicals"]


class BoardSpec(BaseModel):
    board_type: BoardType
    length_in: float
    width_in: float
    thickness_in: float
    volume_l: float
    tail: str
    fins: str
    rocker: str


class DayPlan(BaseModel):
    date: str
    board: str = Field(description="Exact name of an owned board from rank_quiver, or 'Rent' or 'Skip'")
    why: str = Field(description="One short sentence tied to that day's waves")


class SaferSpot(BaseModel):
    name: str
    date: str
    why: str


class SafetyAdvice(BaseModel):
    headline: str = Field(description="One plain sentence, e.g. 'Saturday at Uluwatu is too big and heavy for a beginner.'")
    message: str = Field(description="2-3 sentences: what the risk is (from the numbers) and what to do instead")
    safer_days: list[str] = Field(default_factory=list, description="Dates rated go/caution at the chosen spot")
    safer_spots: list[SaferSpot] = Field(default_factory=list, description="Only spots and dates from find_safer_spots rated go")


class BoardRecommendation(BaseModel):
    primary: BoardSpec
    why: list[str] = Field(description="3-6 short reasons, each tied to a specific number or fact (weight, volume, wave height, break type)")
    backup: BoardSpec | None = Field(default=None, description="Second board for different conditions at this spot")
    backup_when: str = ""
    rent_or_buy_advice: str
    catalog_matches: list[str] = Field(default_factory=list, description="Model names returned by search_catalog only")
    safety_notes: list[str] = Field(default_factory=list)
    headline: str = Field(default="", description="One sentence: what to bring or rent for this trip")
    days: list[DayPlan] = Field(default_factory=list, description="One entry per trip day")
    bring: list[str] = Field(default_factory=list, description="Owned board names to pack (max 2)")


class SurveySession(BaseModel):
    date: date
    spot: str = Field(min_length=2, max_length=80)
    face_ft: float | None = Field(default=None, ge=0.5, le=40)
    period_s: float | None = Field(default=None, ge=3, le=25)
    best_board: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=200)


class SurveyEntry(BaseModel):
    """One real surfer's answers: body, boards they own, and sessions with the board that worked best."""
    who: str = Field(min_length=1, max_length=40, description="Initials or a nickname; stored publicly")
    weight_kg: float = Field(ge=25, le=180)
    height_cm: float = Field(ge=120, le=220)
    skill: Skill
    fitness: Fitness = "average"
    quiver: list[QuiverBoard] = Field(min_length=1, max_length=6)
    sessions: list[SurveySession] = Field(min_length=1, max_length=8)
    review_note: str = Field(default="", max_length=300, description="Assumptions to double-check")
