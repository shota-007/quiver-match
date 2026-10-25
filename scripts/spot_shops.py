"""Save real surf shops near every curated spot (OpenStreetMap data via Nominatim, paced to 1 request/second).

    python -m scripts.spot_shops

Writes app/data/spot_shops.json: {spot name: [shop, ...]}. Spots already saved are kept; spots within 10 km
of a saved spot reuse its shops (the app re-ranks them by distance to each break).
"""

import asyncio
import json

import httpx

from app import tools


async def main() -> None:
    saved = json.loads(tools.SHOPS_FILE.read_text()) if tools.SHOPS_FILE.exists() else {}
    saved = {k: v for k, v in saved.items() if v}          # re-try spots that came back empty
    by_name = {s["name"]: s for s in tools.SPOTS}
    sem = asyncio.Semaphore(3)

    async def one(client: httpx.AsyncClient, s: dict) -> None:
        near = next((n for n in saved if saved[n] and tools._km(s, by_name[n]) <= 10), None)
        if near:
            saved[s["name"]] = saved[near]
            print(f"{s['name']}: reused {near}", flush=True)
            return
        async with sem:
            for attempt in range(3):
                raw = await tools.fetch_shops_raw(client, s["lat"], s["lon"])
                if raw is not None:
                    saved[s["name"]] = raw
                    print(f"{s['name']}: {len(raw)} shops", flush=True)
                    break
                await asyncio.sleep(3 * (attempt + 1))
        tools.SHOPS_FILE.write_text(json.dumps(saved, indent=1))

    async with httpx.AsyncClient() as client:
        for s in tools.SPOTS:           # in order, so nearby spots can reuse what was just saved
            if not saved.get(s["name"]):
                await one(client, s)
    tools.SHOPS_FILE.write_text(json.dumps(saved, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
