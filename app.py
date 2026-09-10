import json
import os
import time
import requests
from datetime import datetime, timezone, timedelta

import fastf1
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify

app = Flask(__name__)

_fastf1_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fastf1_cache')
os.makedirs(_fastf1_cache_dir, exist_ok=True)
fastf1.Cache.enable_cache(_fastf1_cache_dir)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RACES_FILE = os.path.join(BASE_DIR, "2026_f1_races.json")
DRIVERS_FILE = os.path.join(BASE_DIR, "2026_f1_drivers.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
PREDICTIONS_FILE = os.path.join(DATA_DIR, "predictions.json")
RESULTS_FILE = os.path.join(DATA_DIR, "results.json")
CANCELLED_FILE = os.path.join(DATA_DIR, "cancelled.json")
PREV_RESULTS_FILE = os.path.join(DATA_DIR, "previous_results.json")
PREVIOUS_YEAR = 2025

PLAYERS = ["Carmen", "Mark", "BOT-tas"]

# Map race countries to flag filenames
COUNTRY_FLAGS = {
    "Australia": "au.png", "Austria": "at.png", "Azerbaijan": "az.png",
    "Bahrain": "bh.png", "Belgium": "be.png", "Brazil": "br.png",
    "Canada": "ca.png", "China": "cn.png", "Great Britain": "gb.png",
    "Hungary": "hu.png", "Italy": "it.png", "Japan": "jp.png",
    "Mexico": "mx.png", "Monaco": "mc.png", "Netherlands": "nl.png",
    "Qatar": "qa.png", "Saudi Arabia": "sa.png", "Singapore": "sg.png",
    "Spain": "es.png", "United Arab Emirates": "ae.png", "United States": "us.png",
}
TEAM_ICON_MAP = {
    "Alpine F1 Team": "alpine",
    "Haas F1 Team": "haas",
    "RB F1 Team": "racing_bulls",
    "Red Bull": "red_bull_racing",
    "Sauber": "audi",
    "Cadillac F1 Team": "cadillac",
}
SUBJECTIVE_CATEGORIES = {"surprise", "flop"}
BASE_CATEGORIES = ["surprise", "flop", "pole", "third", "second", "winner"]
SPRINT_CATEGORIES = ["sprint_pole", "sprint_winner"]
CATEGORY_LABELS = {
    "pole": "Pole Position",
    "winner": "Race Winner",
    "second": "2nd Place",
    "third": "3rd Place",
    "surprise": "Surprise",
    "flop": "Flop",
    "sprint_pole": "Sprint Pole",
    "sprint_winner": "Sprint Winner",
}


# --- Data helpers ---

def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_races():
    return load_json(RACES_FILE, [])


def load_drivers():
    """Every driver seen this season, including those no longer on the grid.

    Saved predictions and results reference drivers by abbreviation, so past
    races only render correctly if drivers are kept here once they appear.
    """
    drivers = load_json(DRIVERS_FILE, [])
    for d in drivers:
        d.setdefault("status", "active")
    drivers.sort(key=lambda d: d["abbreviation"])
    return drivers


def active_drivers():
    """Only drivers currently on the grid — for picking, not for lookups."""
    return [d for d in load_drivers() if d.get("status") == "active"]


def load_predictions():
    return load_json(PREDICTIONS_FILE)


def save_predictions(data):
    save_json(PREDICTIONS_FILE, data)


def load_results():
    return load_json(RESULTS_FILE)


def save_results(data):
    save_json(RESULTS_FILE, data)


def load_cancelled():
    return set(load_json(CANCELLED_FILE, []))


def save_cancelled(data):
    save_json(CANCELLED_FILE, sorted(data))


def is_cancelled(round_num):
    return round_num in load_cancelled()


def get_race(round_num):
    for race in load_races():
        if race["round"] == round_num:
            return race
    return None


def categories_for_race(race):
    if race.get("sprint"):
        return ["surprise", "flop", "sprint_pole", "sprint_winner",
                "pole", "third", "second", "winner"]
    return list(BASE_CATEGORIES)


# One-line character profile per 2026 circuit, keyed by the "circuit" field in
# 2026_f1_races.json. Feeds BOT-tas so it can match car/driver strengths to
# the track instead of assuming recent form transfers everywhere.
CIRCUIT_TRAITS = {
    "Albert Park Circuit": "Fast flowing semi-street park track; medium-high downforce; overtaking moderate; smooth surface, low tyre wear.",
    "Shanghai International Circuit": "Long back straight with a heavy-braking hairpin; medium downforce; overtaking easy on the main straight; abrasive surface, high tyre wear.",
    "Suzuka International Racing Course": "High-downforce figure-8 with technical esses; overtaking hard (mainly turn 1); medium tyre wear; precision rewarded.",
    "Bahrain International Circuit": "Power track with heavy braking zones; overtaking easy (multiple DRS zones); high tyre wear on an abrasive surface.",
    "Jeddah Corniche Circuit": "Fastest street circuit, very high average speed and close walls; medium downforce; overtaking moderate; low tyre wear.",
    "Miami International Autodrome": "Temporary street-style track, bumpy with three straights; low-medium downforce; overtaking easy into turn 1; low tyre wear.",
    "Circuit Gilles Villeneuve": "Low-downforce stop-go track with punishing walls and kerbs; overtaking easy into the final chicane; low tyre wear.",
    "Circuit de Monaco": "Slowest, tightest street track; maximum downforce; overtaking nearly impossible — qualifying position is decisive.",
    "Circuit de Barcelona-Catalunya": "Medium-high downforce with a long run into turn 1; overtaking moderate; abrasive surface, high tyre wear.",
    "Red Bull Ring": "Short lap with big elevation changes; medium downforce; overtaking easy on long straights; low tyre wear.",
    "Silverstone Circuit": "High-speed flowing corners; medium-high downforce; overtaking moderate; medium-high tyre wear.",
    "Circuit de Spa-Francorchamps": "Longest lap, low-medium downforce, changeable weather; overtaking easy down the Kemmel straight.",
    "Hungaroring": "Tight and twisty, often called Monaco without the walls; medium-high downforce; overtaking hard; hot track, medium tyre wear.",
    "Circuit Zandvoort": "Short lap with banked corners, street-like walls; medium-high downforce; overtaking hard; low-medium tyre wear.",
    "Autodromo Nazionale Monza": "Temple of speed, lowest downforce, slipstream and braking power critical; overtaking easy; low tyre wear.",
    "Circuito IFEMA Madrid": "Brand-new semi-street circuit (Madring) with slow technical sections; overtaking limited; medium tyre wear; no prior form guide.",
    "Baku City Circuit": "Narrow castle section then a 2.2km flat-out straight; low-medium downforce; overtaking easy on the straight; low tyre wear.",
    "Marina Bay Street Circuit": "Humid night street race, bumpy, maximum downforce; overtaking moderate at best; low tyre wear.",
    "Circuit of the Americas": "Technical first sector, big elevation changes, long back straight; medium downforce; overtaking easy into turn 1; medium tyre wear.",
    "Autodromo Hermanos Rodriguez": "High altitude thins the air, cutting downforce and cooling; overtaking moderate on the run to turn 1; low tyre wear.",
    "Autodromo Jose Carlos Pace (Interlagos)": "Short bumpy anticlockwise lap with elevation change, rain is common; medium downforce; overtaking moderate; low-medium tyre wear.",
    "Las Vegas Strip Circuit": "Cold night race, low downforce and very long straights; overtaking easy; low tyre wear but cold grip is tricky.",
    "Lusail International Circuit": "Flowing high-speed night track with aggressive kerbs; medium-high downforce; overtaking moderate; high tyre wear.",
    "Yas Marina Circuit": "Twilight race, low-medium downforce with long straights; overtaking moderate-easy; low tyre wear, grip builds during the race.",
}


def circuit_traits_str(circuit):
    return CIRCUIT_TRAITS.get(circuit, "No circuit profile available.")


def driver_map():
    """abbreviation -> driver dict"""
    return {d["abbreviation"]: d for d in load_drivers()}


def compute_scores(actuals, predictions_round, approvals=None):
    """Return {player: score} for a single round."""
    scores = {}
    for player in PLAYERS:
        preds = predictions_round.get(player, {})
        score = 0
        for cat in actuals:
            if cat in SUBJECTIVE_CATEGORIES and approvals:
                if approvals.get(player, {}).get(cat):
                    score += 1
            else:
                if preds.get(cat) == actuals[cat]:
                    score += 1
        scores[player] = score
    return scores


def deadline_warning(race):
    """Return a warning string if we're within 2 days of race time, else None."""
    try:
        race_dt = datetime.fromisoformat(race["race_time_utc"].replace("Z", "+00:00"))
        cutoff = race_dt - timedelta(days=2)
        if datetime.now(timezone.utc) > cutoff:
            return f"Heads up: race is on {race_dt.strftime('%b %d %H:%M UTC')} — predictions may be late!"
    except Exception:
        pass
    return None


# -- Previous year results helpers --

# Location overrides: 2026 location -> 2025 location (for mismatches)
_LOCATION_OVERRIDES = {
    "Miami": "Miami Gardens",
    "Monte Carlo": "Monaco",
    "Montreal": "Montréal",
    "Sao Paulo": "São Paulo",
    "Yas Marina": "Yas Island",
    "Singapore": "Marina Bay",
}
_NO_PREVIOUS = {"Madrid"}

_schedule_2025 = None


def _get_2025_schedule():
    global _schedule_2025
    if _schedule_2025 is None:
        _schedule_2025 = fastf1.get_event_schedule(PREVIOUS_YEAR)
    return _schedule_2025


def _find_2025_round(location):
    """Find the 2025 round number for a given 2026 location. Returns (round_num, event_row) or (None, None)."""
    if location in _NO_PREVIOUS:
        return None, None
    lookup = _LOCATION_OVERRIDES.get(location, location)
    schedule = _get_2025_schedule()
    for _, row in schedule.iterrows():
        if row.get("RoundNumber", 0) == 0:
            continue
        if row.get("Location", "").lower() == lookup.lower():
            return int(row["RoundNumber"]), row
    return None, None


def _get_ergast_circuit_id(location):
    """Find the Ergast circuitId for a 2026 location by checking a recent schedule."""
    import fastf1.ergast
    ergast = fastf1.ergast.Ergast()
    lookup = _LOCATION_OVERRIDES.get(location, location)
    for year in (2025, 2024):
        try:
            sched = ergast.get_race_schedule(season=year)
            for _, row in sched.iterrows():
                if row.get("locality", "").lower() == lookup.lower():
                    return row["circuitId"]
        except Exception:
            continue
    return None


def _build_historical_stats(circuit_id, active_abbrs):
    """Build podium stats for active drivers at a circuit using Ergast (lightweight).
    Returns {"race": [...], "sprint": [...]} where each entry is
    {"abbr": "VER", "wins": N, "seconds": N, "thirds": N} sorted by wins desc.
    Sprint entries only have {"abbr": "VER", "wins": N}.
    """
    import fastf1.ergast
    ergast = fastf1.ergast.Ergast()

    race_stats = {}   # abbr -> [wins, seconds, thirds]
    sprint_stats = {}  # abbr -> wins

    for year in range(2015, PREVIOUS_YEAR + 1):
        try:
            sched = ergast.get_race_schedule(season=year)
            match = sched[sched["circuitId"] == circuit_id]
            if match.empty:
                continue
            rnd = int(match.iloc[0]["round"])
        except Exception:
            continue

        # Race results
        try:
            res = ergast.get_race_results(season=year, round=rnd)
            if res.content:
                for _, row in res.content[0].iterrows():
                    abbr = row.get("driverCode", "")
                    pos = row.get("position")
                    if abbr not in active_abbrs or pos not in (1, 2, 3):
                        continue
                    if abbr not in race_stats:
                        race_stats[abbr] = [0, 0, 0]
                    race_stats[abbr][pos - 1] += 1
        except Exception:
            pass

        # Sprint results
        try:
            res = ergast.get_sprint_results(season=year, round=rnd)
            if res.content:
                for _, row in res.content[0].iterrows():
                    abbr = row.get("driverCode", "")
                    pos = row.get("position")
                    if abbr not in active_abbrs or pos != 1:
                        continue
                    sprint_stats[abbr] = sprint_stats.get(abbr, 0) + 1
        except Exception:
            pass

    race_list = [
        {"abbr": a, "wins": s[0], "seconds": s[1], "thirds": s[2]}
        for a, s in race_stats.items()
    ]
    race_list.sort(key=lambda x: (x["wins"], x["seconds"], x["thirds"]), reverse=True)

    sprint_list = [
        {"abbr": a, "wins": w}
        for a, w in sprint_stats.items()
    ]
    sprint_list.sort(key=lambda x: x["wins"], reverse=True)

    return {"race": race_list, "sprint": sprint_list}


def load_previous_results():
    return load_json(PREV_RESULTS_FILE)


def save_previous_results(data):
    save_json(PREV_RESULTS_FILE, data)


# --- Routes ---

@app.route("/")
def index():
    races = load_races()
    results = load_results()
    predictions = load_predictions()
    cancelled = load_cancelled()
    totals = {p: 0 for p in PLAYERS}
    race_scores = []
    for race in races:
        rnd = str(race["round"])
        res = results.get(rnd)
        predicted = rnd in predictions and any(predictions[rnd].get(p) for p in PLAYERS)
        is_canc = race["round"] in cancelled
        if res:
            scores = res.get("scores", {})
            for p in PLAYERS:
                totals[p] += scores.get(p, 0)
            race_scores.append({"race": race, "scores": scores, "awarded": True, "predicted": predicted, "cancelled": is_canc})
        else:
            race_scores.append({"race": race, "scores": {}, "awarded": False, "predicted": predicted, "cancelled": is_canc})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc)
    next_race = None
    for race in races:
        race_time = datetime.fromisoformat(race["race_time_utc"].replace("Z", "+00:00"))
        if race_time > now and race["round"] not in cancelled:
            next_race = race
            break
    saved = request.args.get("saved")
    return render_template("index.html", players=PLAYERS, totals=totals, race_scores=race_scores, country_flags=COUNTRY_FLAGS, today=today, next_race=next_race, saved=saved)


@app.route("/predict")
def predict_list():
    races = load_races()
    predictions = load_predictions()
    results = load_results()
    cancelled = load_cancelled()
    race_info = []
    for race in races:
        rnd = str(race["round"])
        has_predictions = rnd in predictions and any(predictions[rnd].get(p) for p in PLAYERS)
        has_results = rnd in results
        race_info.append({"race": race, "has_predictions": has_predictions, "has_results": has_results, "is_cancelled": race["round"] in cancelled})
    return render_template("predict.html", race_info=race_info)


@app.route("/predict/<int:round_num>", methods=["GET", "POST"])
def predict_round(round_num):
    race = get_race(round_num)
    if not race:
        return "Race not found", 404
    if is_cancelled(round_num):
        return redirect(url_for("predict_list"))
    rnd = str(round_num)
    cats = categories_for_race(race)
    drivers = load_drivers()
    dmap = driver_map()
    predictions = load_predictions()
    warning = deadline_warning(race)

    if request.method == "POST":
        round_preds = predictions.get(rnd, {})
        for player in PLAYERS:
            player_preds = {}
            for cat in cats:
                val = request.form.get(f"{player}_{cat}", "").strip()
                if val:
                    player_preds[cat] = val
            round_preds[player] = player_preds
        predictions[rnd] = round_preds
        save_predictions(predictions)
        return redirect(url_for("predict_round", round_num=round_num, saved=1))

    existing = predictions.get(rnd, {})
    saved = request.args.get("saved")
    location_slug = race["location"].lower().replace(" ", "_")
    track_img = f"medium_tracks/round_{round_num:02d}_{location_slug}.png"
    return render_template(
        "predict_form.html",
        race=race,
        categories=cats,
        cat_labels=CATEGORY_LABELS,
        drivers=drivers,
        players=PLAYERS,
        existing=existing,
        warning=warning,
        saved=saved,
        track_img=track_img,
    )


OPENCODE_URL = os.environ.get(
    "OPENCODE_URL", "https://opencode.ai/zen/go/v1/chat/completions"
)
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "glm-5.3-flash")
# Must stay comfortably under the gunicorn worker timeout (see pfun.service),
# otherwise the worker is killed and the client gets an HTML error page.
OPENCODE_TIMEOUT = int(os.environ.get("OPENCODE_TIMEOUT", "120"))
OPENCODE_API_KEY = os.environ.get("OPENCODE_GO_API_KEY", "")


@app.route("/ai/bot-tas/<int:round_num>")
def ai_bottas_predict(round_num):
    race = get_race(round_num)
    if not race:
        return jsonify({"error": "Race not found"}), 404

    # BOT-tas predicts a race, so it picks from the current grid only.
    drivers = active_drivers()

    # Gather context: Standings. Never let a slow/failing Ergast call sink the
    # whole request — the AI picks are still useful without standings.
    ds, cs = [], []
    try:
        import fastf1.ergast
        ergast = fastf1.ergast.Ergast()
        ds, cs = _fetch_standings(ergast, 2026)
        if not ds:
            ds, cs = _fallback_standings_from_2025(ergast)
    except Exception:
        ds, cs = [], []

    # Show the whole grid, not just the top 10: surprise/flop picks can come
    # from any active driver, so everyone needs current data. Drivers who have
    # not yet scored are appended at the end so no one is invisible.
    def _norm(name):
        import unicodedata
        return "".join(
            c for c in unicodedata.normalize("NFKD", name.lower())
            if not unicodedata.combining(c)
        )

    standings_str = "\n".join(
        [f"{r['position']}. {r['givenName']} {r['familyName']} ({r['constructorName']}) - {r['points']} pts" for r in ds]
    )
    if drivers and ds:
        # Ergast spells names differently from our roster ("Andrea Kimi"
        # Antonelli, "Hülkenberg"), so match on the accent-stripped surname.
        ranked_names = {_norm(r["familyName"]) for r in ds}
        unranked = [
            f"{d['first_name']} {d['last_name']} ({d['team']}) - no points yet"
            for d in drivers
            if _norm(d["last_name"]) not in ranked_names
        ]
        if unranked:
            standings_str += "\nNot yet classified: " + "; ".join(unranked)
    else:
        standings_str = standings_str or "No standings available."

    if cs:
        team_str = "\n".join(
            f"{r['constructorName']} - {r['points']} pts" for r in cs
        )
    else:
        team_str = "No team standings available."

    # Gather context: History
    cache = load_previous_results()
    history = cache.get(race["circuit"])
    history_str = "No historical data available."
    if history and history.get("available"):
        race_history = history.get("sessions", {}).get("race", [])
        history_str = "Previous Race Results:\n" + "\n".join([f"{r['pos']}. {r['abbr']}" for r in race_history[:5]])
        if "stats" in history:
            stats = history["stats"].get("race", [])
            history_str += "\nPodium History:\n" + "\n".join([f"{s['abbr']}: {s['wins']} wins, {s['seconds']} 2nds, {s['thirds']} 3rds" for s in stats[:5]])

    # Gather context: the 2026 season so far. The model's training data
    # predates this season, so the graded actuals from earlier rounds are the
    # strongest signal it can get about current form.
    season_lines = []
    try:
        results = load_results()
        for key in sorted(results, key=int):
            rnd = int(key)
            if rnd >= round_num:
                continue
            actuals = results[key].get("actuals") or {}
            if not any(actuals.get(c) for c in ("winner", "pole")):
                continue
            past = get_race(rnd) or {}
            parts = []
            if actuals.get("winner"):
                parts.append(
                    f"P1 {actuals['winner']} P2 {actuals.get('second', '?')} "
                    f"P3 {actuals.get('third', '?')}"
                )
            if actuals.get("pole"):
                parts.append(f"pole {actuals['pole']}")
            if actuals.get("sprint_winner"):
                parts.append(
                    f"sprint win {actuals['sprint_winner']} (pole {actuals.get('sprint_pole', '?')})"
                )
            season_lines.append(f"R{rnd} {past.get('name', '')}: " + ", ".join(parts))
    except Exception:
        season_lines = []
    # Keep the prompt compact: only the most recent rounds.
    season_str = "\n".join(season_lines[-8:]) or "No 2026 races completed yet."

    cats = categories_for_race(race)
    cat_list = ", ".join([CATEGORY_LABELS.get(c, c) for c in cats])
    
    valid_abbrs = [d["abbreviation"] for d in drivers]
    # Spell the roster out in full: given only bare 3-letter codes the model
    # falls back on abbreviations it remembers from other seasons.
    roster_str = "\n".join(
        f"{d['abbreviation']} = {d['first_name']} {d['last_name']} ({d['team']})" for d in drivers
    )
    # Build the example from the real roster so it can never demonstrate a
    # driver who is not racing this season, or a category not being asked for.
    example = {c: valid_abbrs[i % len(valid_abbrs)] for i, c in enumerate(cats)}
    example_str = json.dumps(example, indent=4)

    prompt = f"""
    You are BOT-tas, a seasoned F1 driver and expert analyst.
    Your task is to predict the outcomes for the 2026 {race['name']} at {race['location']}.

    Current Driver Standings (whole grid):
    {standings_str}

    Team Standings:
    {team_str}

    Circuit History ({race['circuit']}):
    {history_str}

    Circuit Character:
    {circuit_traits_str(race['circuit'])}

    2026 Season So Far (graded actual results — your most reliable data, since
    your training knowledge of this season does not exist):
    {season_str}

    The 2026 grid is exactly these {len(drivers)} drivers, and no others:
    {roster_str}

    Categories to predict: {cat_list}

    Alongside the picks, include a "reasoning" key: roughly 200 words in
    English explaining your picks — which form, team, or track factors drove
    each choice.

    RULES:
    - Base your picks on the 2026 Season So Far results and the standings, NOT
      on career reputation or pre-2026 team hierarchies — cars and form have
      changed since then.
    - Weigh the Circuit Character profile: favor the drivers and teams whose
      strengths fit this specific track — form at recent tracks does not
      automatically transfer.
    - For Surprise, look across the WHOLE grid for a driver whose 2026 results
      diverge favorably from what their team's strength suggests. For Flop,
      do the opposite: a driver underperforming relative to their car.
    - Every value MUST be one of these exact codes: {", ".join(valid_abbrs)}
    - Do NOT invent codes, and do NOT name drivers who are absent from the list
      above. Any code outside that list is a wrong answer.
    - Return a value for EVERY one of these keys: {", ".join(cats)}
    - Use the 3-letter code, not the driver's name.

    Example of the required format:
    {example_str}

    Return ONLY the JSON object. Be bold but realistic.
    """

    # Constrain the model at decode time so an out-of-roster code cannot be
    # produced in the first place (server-side JSON schema enforcement).
    schema = {
        "type": "object",
        "properties": {
            **{c: {"type": "string", "enum": valid_abbrs} for c in cats},
            # The reasoning prose itself is not constrained beyond being a
            # string; requiring it makes the model emit it, and a schema
            # failure just falls back to plain JSON mode.
            "reasoning": {"type": "string"},
        },
        "required": list(cats) + ["reasoning"],
    }

    # OPENCODE_TIMEOUT is the budget for the whole request, not per call — the
    # fallback and retry below must not stack past the gunicorn worker limit.
    deadline = time.monotonic() + OPENCODE_TIMEOUT

    session_id = f"pfun-bottas-r{round_num}-{int(time.time())}"

    def _ask(schema):
        remaining = deadline - time.monotonic()
        if remaining < 5:
            raise TimeoutError("BOT-tas ran out of time")
        body = {
            "model": OPENCODE_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "prediction", "schema": schema},
            }
        resp = requests.post(
            OPENCODE_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {OPENCODE_API_KEY}",
                "User-Agent": "pfun-bottas/1.0",
                "x-opencode-session": session_id,
            },
            timeout=remaining,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return {"response": content}

    # Accept a full or last name too, in case the model ignores the code rule.
    name_to_abbr = {}
    for d in drivers:
        name_to_abbr[d["last_name"].upper()] = d["abbreviation"]
        name_to_abbr[f"{d['first_name']} {d['last_name']}".upper()] = d["abbreviation"]

    def _clean(prediction):
        valid = set(valid_abbrs)
        out = {}
        for cat in cats:
            val = str(prediction.get(cat, "")).strip().upper()
            if val in valid:
                out[cat] = val
            elif val in name_to_abbr:
                out[cat] = name_to_abbr[val]
        return out

    def _parse_json(text):
        text = (text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    try:
        try:
            ai_data = _ask(schema)
        except Exception:
            # The endpoint may reject a response_format schema — fall back to
            # a plain completion and lean on the prompt plus validation instead.
            ai_data = _ask(None)

        parsed = _parse_json(ai_data.get("response"))
        cleaned = _clean(parsed)
        reasoning = str(parsed.get("reasoning") or "").strip()

        # One retry if the model still left categories unfilled.
        if len(cleaned) < len(cats):
            try:
                retry = _ask(schema)
                retry_parsed = _parse_json(retry.get("response"))
                merged = _clean(retry_parsed)
                merged.update(cleaned)
                if len(merged) > len(cleaned):
                    cleaned = merged
                    ai_data = retry
                    if not reasoning:
                        reasoning = str(retry_parsed.get("reasoning") or "").strip()
            except Exception:
                pass

        return jsonify({
            "prediction": cleaned,
            "reasoning": reasoning,
            "raw": ai_data.get("response"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/predict/<int:round_num>/previous")
def fetch_previous_results(round_num):
    race = get_race(round_num)
    if not race:
        return jsonify({"available": False, "message": "Race not found"}), 404

    cache = load_previous_results()
    circuit_key = race["circuit"]

    if circuit_key in cache:
        return jsonify(cache[circuit_key])

    round_2025, event = _find_2025_round(race["location"])
    if round_2025 is None:
        result = {"available": False, "message": "No previous race at this circuit"}
        cache[circuit_key] = result
        save_previous_results(cache)
        return jsonify(result)

    has_sprint = event.get("EventFormat", "") in ("sprint_shootout", "sprint_qualifying")
    session_types = [("Q", "qualifying"), ("R", "race")]
    if has_sprint:
        session_types.extend([("SQ", "sprint_qualifying"), ("S", "sprint_race")])

    result = {"available": True, "gp_name": event.get("EventName", ""), "sessions": {}}
    for sess_id, sess_key in session_types:
        try:
            session = fastf1.get_session(PREVIOUS_YEAR, round_2025, sess_id)
            session.load()
            drivers_order = []
            for _, row in session.results.iterrows():
                pos = row.get("Position")
                try:
                    pos = int(pos)
                except (TypeError, ValueError):
                    pos = len(drivers_order) + 1
                drivers_order.append({"pos": pos, "abbr": row["Abbreviation"]})
            drivers_order.sort(key=lambda d: d["pos"])
            result["sessions"][sess_key] = drivers_order
        except Exception:
            pass

    # Historical podium stats for active drivers at this circuit
    active_abbrs = {d["abbreviation"] for d in load_drivers()}
    circuit_id = _get_ergast_circuit_id(race["location"])
    if circuit_id:
        try:
            result["stats"] = _build_historical_stats(circuit_id, active_abbrs)
        except Exception:
            pass

    cache[circuit_key] = result
    save_previous_results(cache)
    return jsonify(result)


@app.route("/award")
def award_list():
    races = load_races()
    predictions = load_predictions()
    results = load_results()
    cancelled = load_cancelled()
    race_info = []
    for race in races:
        rnd = str(race["round"])
        has_predictions = rnd in predictions and any(predictions[rnd].get(p) for p in PLAYERS)
        has_results = rnd in results
        race_info.append({"race": race, "has_predictions": has_predictions, "has_results": has_results, "is_cancelled": race["round"] in cancelled})
    return render_template("award.html", race_info=race_info)


@app.route("/award/<int:round_num>/cancel", methods=["POST"])
def toggle_cancel(round_num):
    race = get_race(round_num)
    if not race:
        return "Race not found", 404
    cancelled = load_cancelled()
    if round_num in cancelled:
        cancelled.discard(round_num)
    else:
        cancelled.add(round_num)
    save_cancelled(cancelled)
    return redirect(url_for("award_list"))


@app.route("/award/<int:round_num>", methods=["GET", "POST"])
def award_round(round_num):
    race = get_race(round_num)
    if not race:
        return "Race not found", 404
    if is_cancelled(round_num):
        return redirect(url_for("award_list"))
    rnd = str(round_num)
    cats = categories_for_race(race)
    drivers = load_drivers()
    dmap = driver_map()
    predictions = load_predictions()
    results = load_results()
    existing_result = results.get(rnd, {})
    existing_actuals = existing_result.get("actuals", {})

    comparison = None
    actuals_draft = None
    approvals_draft = None
    preview_scores = None

    if request.method == "POST":
        if "confirm" in request.form:
            # Second step: save
            actuals = {}
            for cat in cats:
                if cat not in SUBJECTIVE_CATEGORIES:
                    val = request.form.get(f"actual_{cat}", "").strip()
                    if val:
                        actuals[cat] = val
                else:
                    actuals[cat] = ""
            round_preds = predictions.get(rnd, {})
            approvals = {}
            for player in PLAYERS:
                approvals[player] = {}
                for cat in SUBJECTIVE_CATEGORIES:
                    if cat in cats and request.form.get(f"approve_{player}_{cat}"):
                        approvals[player][cat] = True
            scores = compute_scores(actuals, round_preds, approvals=approvals)
            results[rnd] = {"actuals": actuals, "approvals": approvals, "scores": scores}
            save_results(results)
            return redirect(url_for("index", saved=1))
        else:
            # First step: preview comparison
            actuals_draft = {}
            for cat in cats:
                if cat not in SUBJECTIVE_CATEGORIES:
                    val = request.form.get(f"actual_{cat}", "").strip()
                    if val:
                        actuals_draft[cat] = val
                else:
                    actuals_draft[cat] = ""
            round_preds = predictions.get(rnd, {})
            # Read subjective approvals
            approvals_draft = {}
            for player in PLAYERS:
                approvals_draft[player] = {}
                for cat in SUBJECTIVE_CATEGORIES:
                    if cat in cats and request.form.get(f"approve_{player}_{cat}"):
                        approvals_draft[player][cat] = True
            comparison = []
            for cat in cats:
                actual = actuals_draft.get(cat, "")
                row = {"category": CATEGORY_LABELS.get(cat, cat), "cat_key": cat, "actual": actual, "actual_abbr": actual, "players": {}}
                for player in PLAYERS:
                    pred = round_preds.get(player, {}).get(cat, "")
                    if cat in SUBJECTIVE_CATEGORIES:
                        correct = approvals_draft.get(player, {}).get(cat, False)
                    else:
                        correct = pred == actual and actual != ""
                    row["players"][player] = {"pred": pred, "correct": correct}
                comparison.append(row)
            # Compute preview scores
            preview_scores = compute_scores(actuals_draft, round_preds, approvals=approvals_draft)

    saved = request.args.get("saved")
    location_slug = race["location"].lower().replace(" ", "_")
    track_img = f"medium_tracks/round_{round_num:02d}_{location_slug}.png"
    round_preds = predictions.get(rnd, {})
    return render_template(
        "award_form.html",
        race=race,
        categories=cats,
        cat_labels=CATEGORY_LABELS,
        drivers=drivers,
        dmap=dmap,
        players=PLAYERS,
        existing_actuals=existing_actuals,
        comparison=comparison,
        actuals_draft=actuals_draft,
        approvals_draft=approvals_draft if comparison else None,
        preview_scores=preview_scores if comparison else None,
        saved=saved,
        track_img=track_img,
        subjective_cats=SUBJECTIVE_CATEGORIES,
        round_preds=round_preds,
    )


@app.route("/award/<int:round_num>/fetch")
def fetch_results(round_num):
    race = get_race(round_num)
    if not race:
        return jsonify({"results": {}, "errors": ["Race not found"]}), 404

    year = 2026
    results = {}
    errors = []

    # Map: (session_identifier, position) -> result key
    session_map = [
        ("Q", 0, "pole"),
        ("R", 0, "winner"),
        ("R", 1, "second"),
        ("R", 2, "third"),
    ]
    if race.get("sprint"):
        session_map.extend([
            ("SQ", 0, "sprint_pole"),
            ("S", 0, "sprint_winner"),
        ])

    # Group by session to avoid loading the same session twice
    from collections import defaultdict
    session_needs = defaultdict(list)
    for sess_id, pos, key in session_map:
        session_needs[sess_id].append((pos, key))

    failed_sessions = set()
    session_labels = {"Q": "Qualifying", "R": "Race", "SQ": "Sprint Qualifying", "S": "Sprint"}

    for sess_id, extractions in session_needs.items():
        try:
            session = fastf1.get_session(year, round_num, sess_id)
            session.load()
            for pos, key in extractions:
                try:
                    abbr = session.results.iloc[pos]["Abbreviation"]
                    results[key] = abbr
                except (IndexError, KeyError):
                    failed_sessions.add(session_labels.get(sess_id, sess_id))
        except Exception:
            failed_sessions.add(session_labels.get(sess_id, sess_id))

    if failed_sessions:
        # Maintain a consistent display order
        ordered = [l for l in ["Sprint Qualifying", "Sprint", "Qualifying", "Race"] if l in failed_sessions]
        if len(ordered) == 1:
            names = ordered[0]
        elif len(ordered) == 2:
            names = f"{ordered[0]} and {ordered[1]}"
        else:
            names = ", ".join(ordered[:-1]) + f", and {ordered[-1]}"
        errors.append(f"{names} not available")

    return jsonify({"results": results, "errors": errors})


def _fetch_standings(ergast, season):
    """Fetch driver and constructor standings for a season. Returns (drivers, constructors) or (None, None)."""
    try:
        ds = ergast.get_driver_standings(season=season)
        driver_standings = None
        if ds.content and len(ds.content[0]) > 0:
            rows = ds.content[0].to_dict("records")
            for row in rows:
                # Ergast returns constructorNames as a list; template expects constructorName
                if "constructorNames" in row and "constructorName" not in row:
                    names = row.pop("constructorNames")
                    row["constructorName"] = names[0] if names else ""
                row["points"] = int(row.get("points", 0))
            driver_standings = rows
        cs = ergast.get_constructor_standings(season=season)
        if cs.content and len(cs.content[0]) > 0:
            c_rows = cs.content[0].to_dict("records")
            for row in c_rows:
                row["points"] = int(row.get("points", 0))
            constructor_standings = c_rows
        else:
            constructor_standings = None
        if driver_standings or constructor_standings:
            return driver_standings, constructor_standings
    except Exception:
        pass
    return None, None


def _fallback_standings_from_2025(ergast):
    """Build 2026 standings seeded from 2025 final results, with new drivers/teams placed last."""
    drivers_2026 = load_drivers()
    teams_2026 = sorted(set(d["team"] for d in drivers_2026))

    # Fetch 2025 standings
    ds_2025, cs_2025 = _fetch_standings(ergast, 2025)

    # Build driver standings using 2025 order as seed
    driver_standings = []
    used = set()
    if ds_2025:
        for row in ds_2025:
            full_name = f"{row['givenName']} {row['familyName']}"
            # Match against 2026 roster
            match = None
            for d in drivers_2026:
                if d["first_name"] == row.get("givenName") and d["last_name"] == row.get("familyName"):
                    match = d
                    break
            if match and match["abbreviation"] not in used:
                used.add(match["abbreviation"])
                driver_standings.append({
                    "position": len(driver_standings) + 1,
                    "givenName": match["first_name"],
                    "familyName": match["last_name"],
                    "constructorName": match["team"],
                    "points": 0,
                })
    # Append 2026 drivers not in 2025 standings at the end
    for d in sorted(drivers_2026, key=lambda x: (x["last_name"], x["first_name"])):
        if d["abbreviation"] not in used:
            driver_standings.append({
                "position": len(driver_standings) + 1,
                "givenName": d["first_name"],
                "familyName": d["last_name"],
                "constructorName": d["team"],
                "points": 0,
            })

    # Build constructor standings using 2025 order as seed
    constructor_standings = []
    used_teams = set()
    # Map 2025 constructor names to 2026 team names (handle renames)
    TEAM_NAME_MAP_2025_TO_2026 = {
        "Sauber": "Audi",
        "RB F1 Team": "Racing Bulls",
        "Red Bull": "Red Bull Racing",
        "Haas F1 Team": "Haas",
        "Alpine F1 Team": "Alpine",
    }
    if cs_2025:
        for row in cs_2025:
            name_2025 = row.get("constructorName", "")
            name_2026 = TEAM_NAME_MAP_2025_TO_2026.get(name_2025, name_2025)
            if name_2026 in teams_2026 and name_2026 not in used_teams:
                used_teams.add(name_2026)
                constructor_standings.append({
                    "position": len(constructor_standings) + 1,
                    "constructorName": name_2026,
                    "points": 0,
                })
    # Append new 2026 teams at the end
    for team in sorted(teams_2026):
        if team not in used_teams:
            constructor_standings.append({
                "position": len(constructor_standings) + 1,
                "constructorName": team,
                "points": 0,
            })

    return driver_standings, constructor_standings


@app.route("/standings")
def standings():
    import fastf1.ergast
    ergast = fastf1.ergast.Ergast()
    fallback = False

    driver_standings, constructor_standings = _fetch_standings(ergast, 2026)

    if not driver_standings and not constructor_standings:
        driver_standings, constructor_standings = _fallback_standings_from_2025(ergast)
        fallback = True

    return render_template(
        "standings.html",
        driver_standings=driver_standings,
        constructor_standings=constructor_standings,
        fallback=fallback,
        team_icon_map=TEAM_ICON_MAP,
    )


@app.route("/race/<int:round_num>")
def race_detail(round_num):
    race = get_race(round_num)
    if not race:
        return "Race not found", 404
    rnd = str(round_num)
    predictions = load_predictions()
    results = load_results()
    round_preds = predictions.get(rnd, {})
    existing_result = results.get(rnd, {})
    actuals = existing_result.get("actuals", {})
    approvals = existing_result.get("approvals", {})
    scored = bool(existing_result)
    predicted = rnd in predictions and any(round_preds.get(p) for p in PLAYERS)

    if not scored and not predicted:
        return "No predictions or results for this race yet", 404

    cats = categories_for_race(race)
    dmap_ = driver_map()
    comparison = []
    for cat in cats:
        actual = actuals.get(cat, "")
        row = {"category": CATEGORY_LABELS.get(cat, cat), "cat_key": cat, "actual": actual, "players": {}}
        for player in PLAYERS:
            pred = round_preds.get(player, {}).get(cat, "")
            if scored:
                if cat in SUBJECTIVE_CATEGORIES:
                    correct = approvals.get(player, {}).get(cat, False)
                else:
                    correct = pred == actual and actual != ""
            else:
                correct = None
            row["players"][player] = {"pred": pred, "correct": correct}
        comparison.append(row)

    scores = existing_result.get("scores", {}) if scored else None
    location_slug = race["location"].lower().replace(" ", "_")
    track_img = f"medium_tracks/round_{round_num:02d}_{location_slug}.png"
    return render_template(
        "race_detail.html",
        race=race, comparison=comparison, players=PLAYERS, scores=scores,
        scored=scored, dmap=dmap_, track_img=track_img,
        subjective_cats=SUBJECTIVE_CATEGORIES,
        cancelled=is_cancelled(round_num),
    )


@app.route("/flags/<path:filename>")
def serve_flag(filename):
    return send_from_directory(os.path.join(BASE_DIR, "flags"), filename)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
