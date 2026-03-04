import json
import os
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, redirect, url_for, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RACES_FILE = os.path.join(BASE_DIR, "2026_f1_races.json")
DRIVERS_FILE = os.path.join(BASE_DIR, "2026_f1_drivers.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
PREDICTIONS_FILE = os.path.join(DATA_DIR, "predictions.json")
RESULTS_FILE = os.path.join(DATA_DIR, "results.json")

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


def get_race(round_num):
    for race in load_races():
        if race["round"] == round_num:
            return race
    return None


def categories_for_race(race):
    cats = list(BASE_CATEGORIES)
    if race.get("sprint"):
        cats = SPRINT_CATEGORIES + cats
    return cats


def driver_map():
    """abbreviation -> driver dict"""
    return {d["abbreviation"]: d for d in load_drivers()}


def compute_scores(actuals, predictions_round):
    """Return {player: score} for a single round."""
    scores = {}
    for player in PLAYERS:
        preds = predictions_round.get(player, {})
        score = sum(1 for cat in actuals if preds.get(cat) == actuals[cat])
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
    totals = {p: 0 for p in PLAYERS}
    race_scores = []
    for race in races:
        rnd = str(race["round"])
        res = results.get(rnd)
        predicted = rnd in predictions and any(predictions[rnd].get(p) for p in PLAYERS)
        if res:
            scores = res.get("scores", {})
            for p in PLAYERS:
                totals[p] += scores.get(p, 0)
            race_scores.append({"race": race, "scores": scores, "awarded": True, "predicted": predicted})
        else:
            race_scores.append({"race": race, "scores": {}, "awarded": False, "predicted": predicted})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return render_template("index.html", players=PLAYERS, totals=totals, race_scores=race_scores, country_flags=COUNTRY_FLAGS, today=today)


@app.route("/predict")
def predict_list():
    races = load_races()
    predictions = load_predictions()
    results = load_results()
    race_info = []
    for race in races:
        rnd = str(race["round"])
        has_predictions = rnd in predictions and any(predictions[rnd].get(p) for p in PLAYERS)
        has_results = rnd in results
        race_info.append({"race": race, "has_predictions": has_predictions, "has_results": has_results})
    return render_template("predict.html", race_info=race_info)


@app.route("/predict/<int:round_num>", methods=["GET", "POST"])
def predict_round(round_num):
    race = get_race(round_num)
    if not race:
        return "Race not found", 404
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
    )


@app.route("/award")
def award_list():
    races = load_races()
    predictions = load_predictions()
    results = load_results()
    race_info = []
    for race in races:
        rnd = str(race["round"])
        has_predictions = rnd in predictions and any(predictions[rnd].get(p) for p in PLAYERS)
        has_results = rnd in results
        race_info.append({"race": race, "has_predictions": has_predictions, "has_results": has_results})
    return render_template("award.html", race_info=race_info)


@app.route("/award/<int:round_num>", methods=["GET", "POST"])
def award_round(round_num):
    race = get_race(round_num)
    if not race:
        return "Race not found", 404
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

    if request.method == "POST":
        if "confirm" in request.form:
            # Second step: save
            actuals = {}
            for cat in cats:
                val = request.form.get(f"actual_{cat}", "").strip()
                if val:
                    actuals[cat] = val
            round_preds = predictions.get(rnd, {})
            scores = compute_scores(actuals, round_preds)
            results[rnd] = {"actuals": actuals, "scores": scores}
            save_results(results)
            return redirect(url_for("award_round", round_num=round_num, saved=1))
        else:
            # First step: preview comparison
            actuals_draft = {}
            for cat in cats:
                val = request.form.get(f"actual_{cat}", "").strip()
                if val:
                    actuals_draft[cat] = val
            round_preds = predictions.get(rnd, {})
            comparison = []
            for cat in cats:
                actual = actuals_draft.get(cat, "")
                row = {"category": CATEGORY_LABELS.get(cat, cat), "actual": actual, "actual_abbr": actual, "players": {}}
                for player in PLAYERS:
                    pred = round_preds.get(player, {}).get(cat, "")
                    correct = pred == actual and actual != ""
                    row["players"][player] = {"pred": pred, "correct": correct}
                comparison.append(row)
            # Compute preview scores
            preview_scores = compute_scores(actuals_draft, round_preds)

    saved = request.args.get("saved")
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
        preview_scores=preview_scores if comparison else None,
        saved=saved,
    )


@app.route("/flags/<path:filename>")
def serve_flag(filename):
    return send_from_directory(os.path.join(BASE_DIR, "flags"), filename)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
