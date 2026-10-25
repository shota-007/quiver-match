"""Look up a freely licensed photo for each spot on Wikipedia (Wikimedia Commons) and save the links.

    python -m scripts.spot_photos

Writes app/data/spot_photos.json: {spot name: {image, title, page}}. Only links and credits are stored;
the browser loads the image from Wikimedia and the page credits it.
"""

import json
import time

import httpx

from app import tools
from app.config import DATA_DIR

UA = {"User-Agent": "QuiverMatch/1.0 (https://github.com/shota-007; MGT 409 class project) python-httpx"}
DEFAULT = "Tube riding"
CANDIDATES = {
    "South Beach (Crescent City)": ["Crescent City, California"], "Point Arena": ["Point Arena, California"],
    "Salmon Creek": ["Salmon Creek Beach", "Bodega Bay, California"], "Bolinas": ["Bolinas, California"],
    "Ocean Beach SF": ["Ocean Beach, San Francisco"], "Linda Mar (Pacifica)": ["Pacifica State Beach", "Pacifica, California"],
    "Mavericks": ["Mavericks, California"], "Cowell's Beach": ["Cowell's Beach", "Santa Cruz Wharf", "Santa Cruz, California"],
    "Pleasure Point": ["Pleasure Point, California"], "Steamer Lane": ["Steamer Lane", "Santa Cruz, California"],
    "Asilomar": ["Asilomar State Beach", "Pacific Grove, California"], "Sand Dollar Beach (Big Sur)": ["Sand Dollar Beach", "Big Sur"],
    "Morro Bay (The Rock)": ["Morro Rock"], "Pismo Beach Pier": ["Pismo Beach, California"],
    "Jalama Beach": ["Jalama Beach County Park", "Jalama Beach"], "Leadbetter Point": ["Leadbetter Beach", "Santa Barbara, California"],
    "Rincon": ["Rincon Point", "Rincon (surf spot)"], "C-Street (Ventura Point)": ["Surfers' Point", "Ventura, California"],
    "Silver Strand": ["Oxnard, California"], "County Line": ["Leo Carrillo State Park"],
    "Malibu Surfrider (First Point)": ["Malibu Surfrider Beach"], "Zuma Beach": ["Zuma Beach"], "Venice Breakwater": ["Venice Beach"],
    "El Porto": ["Manhattan Beach, California"], "Manhattan Beach Pier": ["Manhattan Beach Pier", "Manhattan Beach, California"],
    "Hermosa Beach Pier": ["Hermosa Beach Pier", "Hermosa Beach, California"], "Lunada Bay": ["Lunada Bay", "Palos Verdes Estates, California"],
    "Seal Beach Pier": ["Seal Beach Pier", "Seal Beach, California"], "Huntington Beach Pier": ["Huntington Beach Pier"],
    "Newport Beach (Blackies)": ["Newport Beach, California"], "The Wedge": ["The Wedge (surfing)"],
    "Salt Creek": ["Salt Creek Beach"], "Doheny State Beach": ["Doheny State Beach"], "Lower Trestles": ["Trestles"],
    "San Onofre (Old Man's)": ["San Onofre State Beach"], "Oceanside Pier": ["Oceanside Pier", "Oceanside, California"],
    "Swami's": ["Swami's", "Encinitas, California"], "Cardiff Reef": ["Cardiff State Beach", "Cardiff-by-the-Sea, Encinitas, California"],
    "Black's Beach": ["Black's Beach"], "Windansea": ["Windansea Beach"], "Pacific Beach (Crystal Pier)": ["Crystal Pier", "Pacific Beach, San Diego"],
    "Ocean Beach San Diego": ["Ocean Beach Pier (San Diego)", "Ocean Beach, San Diego"], "Imperial Beach": ["Imperial Beach, California"],
    "Banzai Pipeline": ["Banzai Pipeline"], "Waikiki (Queens)": ["Waikiki"], "Cocoa Beach": ["Cocoa Beach, Florida"],
    "Rockaway Beach": ["Rockaway Beach, Queens"], "Kuta Beach": ["Kuta Beach", "Kuta, Bali"], "Batu Bolong (Canggu)": ["Canggu"],
    "Keramas": ["Keramas"], "Uluwatu": ["Uluwatu", "Bukit Peninsula"], "Padang Padang": ["Padang Padang Beach", "Padang Padang"],
    "Playa Zicatela": ["Playa Zicatela", "Puerto Escondido, Oaxaca"], "La Punta": ["Puerto Escondido, Oaxaca"],
}


def summary(client: httpx.Client, title: str) -> dict | None:
    for attempt in range(3):
        r = client.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + title.replace(" ", "_"), headers=UA, timeout=10)
        if r.status_code == 429:
            time.sleep(2 + attempt * 3)
            continue
        if r.status_code != 200:
            return None
        j = r.json()
        thumb = (j.get("thumbnail") or {}).get("source")
        if j.get("type") != "standard" or not thumb:
            return None
        return {"image": thumb.replace("/330px-", "/960px-"), "title": j["title"],
                "page": j["content_urls"]["desktop"]["page"]}
    return None


def main() -> None:
    out = {}
    with httpx.Client(follow_redirects=True) as client:
        out["_default"] = summary(client, DEFAULT)
        for s in tools.SPOTS:
            for title in CANDIDATES.get(s["name"], [s["name"]]):
                hit = summary(client, title)
                time.sleep(0.4)
                if hit:
                    out[s["name"]] = hit
                    break
            print(f"{s['name'][:32]:32} -> {out.get(s['name'], {}).get('title', 'none (default barrel)')}")
    (DATA_DIR / "spot_photos.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
