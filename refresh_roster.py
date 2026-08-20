"""Refresh the 2026 driver roster from the Jolpica (Ergast successor) API.

The roster is append-only: a driver who has appeared this season is never
removed, because saved predictions and stored results reference drivers by
abbreviation and past races must keep rendering. Drivers who are no longer on
the grid are marked "out" instead of deleted.

The API only reports drivers who have actually taken part in a completed
session, so it lags any mid-break driver change by a race weekend. Announced
but not-yet-raced changes go in roster_overrides.json, which wins over the feed.

Usage:
    python refresh_roster.py            # show what would change
    python refresh_roster.py --write    # apply the changes
"""

import json
import os
import sys
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVERS_FILE = os.path.join(BASE_DIR, "2026_f1_drivers.json")
OVERRIDES_FILE = os.path.join(BASE_DIR, "roster_overrides.json")
SEASON = 2026
API = "https://api.jolpi.ca/ergast/f1"
TIMEOUT = 30

# Jolpica reports constructors by their formal entrant name; the app uses the
# short names that TEAM_ICON_MAP and the templates already expect.
TEAM_NAMES = {
    "Red Bull": "Red Bull Racing",
    "RB F1 Team": "Racing Bulls",
    "Alpine F1 Team": "Alpine",
    "Haas F1 Team": "Haas",
    "Cadillac F1 Team": "Cadillac",
    "Sauber": "Audi",
}

NATIONALITY_FLAGS = {
    "British": "gb", "Dutch": "nl", "Spanish": "es", "Monegasque": "mc",
    "Mexican": "mx", "French": "fr", "German": "de", "Finnish": "fi",
    "Australian": "au", "Canadian": "ca", "Japanese": "jp", "Thai": "th",
    "Italian": "it", "Danish": "dk", "Chinese": "cn", "American": "us",
    "Brazilian": "br", "Argentine": "ar", "New Zealander": "nz",
    "Argentinian": "ar", "Swedish": "se", "Belgian": "be", "Austrian": "at",
}


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fetch_current_grid():
    """Return {abbreviation: {...}} for drivers in the most recent race."""
    resp = requests.get(f"{API}/{SEASON}/last/results/?limit=100", timeout=TIMEOUT)
    resp.raise_for_status()
    races = resp.json()["MRData"]["RaceTable"]["Races"]
    if not races:
        raise SystemExit(f"No {SEASON} race results published yet — nothing to refresh.")

    race = races[0]
    grid = {}
    for result in race["Results"]:
        d = result["Driver"]
        code = d.get("code")
        if not code:
            # Reserve/test drivers appear without a code; they never race.
            continue
        team = result["Constructor"]["name"]
        grid[code] = {
            "first_name": d["givenName"],
            "last_name": d["familyName"],
            "abbreviation": code,
            "nationality": d.get("nationality", ""),
            "team": TEAM_NAMES.get(team, team),
        }
    return grid, f"round {race['round']} ({race['raceName']}, {race['date']})"


def flag_for(nationality, existing=None):
    if existing:
        return existing
    code = NATIONALITY_FLAGS.get(nationality)
    return f"flags/{code}.png" if code else ""


def merge(roster, grid, overrides):
    """Merge feed + overrides into the roster. Returns (new_roster, changes)."""
    by_abbr = {d["abbreviation"]: dict(d) for d in roster}
    changes = []

    # Overrides describe the grid as it stands now, ahead of the feed.
    effective = dict(grid)
    for abbr, entry in overrides.get("drivers", {}).items():
        merged = dict(effective.get(abbr, {}))
        merged.update(entry)
        merged["abbreviation"] = abbr
        effective[abbr] = merged
    for abbr in overrides.get("out", []):
        effective.pop(abbr, None)

    for abbr, info in sorted(effective.items()):
        source = " (override)" if abbr in overrides.get("drivers", {}) else ""
        if abbr not in by_abbr:
            entry = dict(info)
            entry["nationality"] = entry.get("nationality", "")
            entry["flag"] = flag_for(entry["nationality"])
            entry["status"] = "active"
            by_abbr[abbr] = entry
            changes.append(f"  + {abbr} {entry['first_name']} {entry['last_name']} "
                           f"joins {entry['team']}{source}")
            if not entry["flag"]:
                changes.append(f"    ! no flag for nationality "
                               f"{entry['nationality']!r} — set 'flag' by hand")
            continue

        current = by_abbr[abbr]
        if info.get("team") and current.get("team") != info["team"]:
            changes.append(f"  ~ {abbr} {current.get('team')} -> {info['team']}{source}")
            current["team"] = info["team"]
        # A missing status is an entry from before statuses existed: backfill it
        # silently, and only report a genuine return to the grid.
        if current.get("status", "active") != "active":
            changes.append(f"  ~ {abbr} returns to the grid{source}")
        current["status"] = "active"
        current.setdefault("flag", flag_for(current.get("nationality", "")))

    # Anyone on file but not on the current grid is out, never deleted.
    for abbr, entry in by_abbr.items():
        if abbr not in effective and entry.get("status") != "out":
            changes.append(f"  - {abbr} {entry['first_name']} {entry['last_name']} "
                           f"no longer on the grid — marked out (totals preserved)")
            entry["status"] = "out"
        entry.setdefault("status", "active")

    new_roster = sorted(by_abbr.values(), key=lambda d: d["abbreviation"])
    return new_roster, changes


def main():
    write = "--write" in sys.argv
    roster = load_json(DRIVERS_FILE, [])
    overrides = load_json(OVERRIDES_FILE, {})

    grid, source = fetch_current_grid()
    print(f"Feed: {len(grid)} drivers from {source}")
    if overrides.get("drivers") or overrides.get("out"):
        print(f"Overrides: {OVERRIDES_FILE}")

    new_roster, changes = merge(roster, grid, overrides)

    if not changes:
        print("Roster already up to date.")
        return

    print(f"\n{len(changes)} change(s):")
    for line in changes:
        print(line)

    if not write:
        print("\nDry run. Re-run with --write to apply.")
        return

    with open(DRIVERS_FILE, "w") as f:
        json.dump(new_roster, f, indent=2)
        f.write("\n")
    active = sum(1 for d in new_roster if d.get("status") == "active")
    print(f"\nWrote {DRIVERS_FILE}: {active} active, {len(new_roster) - active} out.")


if __name__ == "__main__":
    main()
