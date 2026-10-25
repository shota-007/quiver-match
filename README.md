# Quiver Match

**An AI agent app for everyone from first-timers to experienced surfers: which board to ride or rent for the real waves at your spot, which nearby shop has it, and whether it's safe for you.**

Enter your weight, height, skill, paddle fitness, the boards you own (your quiver), and a spot plus trip dates (for example *El Porto, next 3 days* or *Uluwatu, Bali*). Quiver Match:

* pulls the real swell forecast for those dates (Open-Meteo Marine, free, no key),
* rates every day **go / caution / no-go** for your level in code, and when a day is risky a **Safety Agent** suggests safer nearby spots and days using their real forecasts,
* ranks your boards for each day with explainable meters (catching ease, control, turning), and tells you what to pack and what to rent,
* shows your boards side by side on a 3D wave driven by the forecast (three.js, "illustrative, not a physics sim"),
* lists real surf shops near the break to rent from or buy at (OpenStreetMap),
* sizes the ideal board to rent or buy, with top and side renders, a shortboard/funboard/longboard comparison, and a wetsuit pick.

## How it works

```
Browser form ──> FastAPI guardrails (input checks, injection screen, rate + token budget)
                     │
                     ▼
            Conditions Agent  ── tools: lookup_spot (curated spot DB / geocoding)
                     │                 get_forecast (Open-Meteo Marine API, live, no key)
                     ▼  ConditionsReport (typed)
              Shaper Agent    ── tools: calc_board (deterministic volume + dimension calculator)
                     │                 search_catalog (real board models)
                     ▼  BoardRecommendation (typed)
               Validator (code) ── overwrites any dimension that does not match the calculator,
                     │              drops board models that are not in the catalog
                     ▼
                  Results page + per-run token usage
```

* Model: `gpt-6-luna` through Portkey (the only model allowed on the course key).
* The AI never makes up board numbers: `calc_board` computes them, and the validator enforces that.
* Every run is logged to `logs/runs.jsonl` (token usage per agent) and `logs/traces/<run_id>.json` (step-by-step trace).

## Run it locally (about 3 minutes)

Requires Python 3.11+.

1. Clone the repo and enter the folder:
   ```bash
   git clone https://github.com/shota-007/quiver-match.git && cd quiver-match
   ```
2. Provide your key. Put a `.env` file **in this folder or in the folder one level up** (the app checks both, in that order). See `.env.example`:
   ```
   PORTKEY_API_KEY=your-key-here
   ```
3. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Start the app:
   ```bash
   uvicorn app.main:app --port 8000
   ```
5. Open http://localhost:8000, fill in the form, and click **Find my board**. A run takes about 15-30 seconds.

Optional command-line run:
```bash
python -m app.cli --weight 75 --height 178 --skill intermediate --spot "El Porto"
```

## Tests, evaluation, and tokenomics

```bash
python -m tests.safety_tests            # 15 attack/malfunction tests, offline, 0 tokens
python -m tests.safety_tests --live     # + 2 live attacks on the real model
python -m eval.run_eval                 # 11 surfer trips: app vs. app (medium effort) vs. plain-LLM baseline
python -m eval.real_surfers --llm       # real surfers' sessions: our pick vs. the board that worked (needs eval/real_surfers.json)
python -m eval.tokenomics --price-in <$/1M> --price-cached <$/1M> --price-out <$/1M>
```

Build the report and slides (self-contained HTML, numbers pulled from the results and logs):

```bash
python -m report.build                  # writes report.html and slides.html
```

Results are written to `eval/results/` (`safety_results.json`, `eval_summary.md`, `eval_results.json`, `tokenomics.md`).

## Data

* `app/data/spots.json`: 47 curated surf spots (43 along the California coast, north to south) (break type, bottom, power, typical size, skill floor). Spots not in the list are geocoded and use the live forecast only.
* `app/data/boards.json`: a small catalog of common board models by type.
* `app/data/spot_shops.json`: real surf shops near each spot from OpenStreetMap (refresh with `python -m scripts.spot_shops`); other places are looked up live.
* `app/data/spot_photos.json`: links to freely licensed Wikipedia / Wikimedia Commons photos of each spot (refresh with `python -m scripts.spot_photos`).
* Live forecasts come from the free [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api). No extra API key is needed.

## Safety defenses

* Input validation (weight, height, and text length ranges) and a prompt-injection screen on free-text fields.
* User text is wrapped as untrusted data in the agent prompts.
* Per-agent request, tool-call, and token limits (stops runaway loops), plus a per-client hourly cap and an app-wide daily token budget.
* Tools can't change the surfer's profile, cap repeated calls, and refuse board types unsafe for the surfer's skill.
* The output validator replaces invented dimensions and removes invented board models.
* All model text is rendered with `textContent` (no HTML injection).

## Acknowledgments

* The "where to rent / where to buy nearby" feature was suggested by the owner of Jack's Surfboards.
* Shop listings © OpenStreetMap contributors. Spot photos from Wikipedia / Wikimedia Commons (credited in the app). Forecasts from Open-Meteo.
