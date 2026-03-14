import json
import os
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

PLAYERS = ["Carmen", "Mark"]

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
    drivers = load_json(DRIVERS_FILE, [])
    drivers.sort(key=lambda d: d["abbreviation"])
    return drivers


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
