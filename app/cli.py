"""Run one recommendation from the terminal: python -m app.cli --weight 75 --height 178 --skill intermediate --spot "El Porto" """

import argparse
import asyncio
import json

from .agents import dump, recommend
from .models import SurferProfile

parser = argparse.ArgumentParser()
parser.add_argument("--weight", type=float, required=True, help="kg")
parser.add_argument("--height", type=float, required=True, help="cm")
parser.add_argument("--skill", required=True)
parser.add_argument("--fitness", default="average")
parser.add_argument("--spot", required=True)
parser.add_argument("--intent", default="buy")
parser.add_argument("--notes", default="")
parser.add_argument("--board-pref", default="auto", help="auto, shortboard, funboard, longboard")
parser.add_argument("--days", type=int, default=3)
parser.add_argument("--quiver", default="", help='JSON list, e.g. [{"board_type":"fish","length_in":70,"volume_l":33}]')
a = parser.parse_args()

profile = SurferProfile(weight_kg=a.weight, height_cm=a.height, skill=a.skill, fitness=a.fitness,
                        spot=a.spot, intent=a.intent, notes=a.notes, board_pref=a.board_pref,
                        days=a.days, quiver=json.loads(a.quiver) if a.quiver else [])
print(dump(asyncio.run(recommend(profile))))
