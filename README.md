# P-Fun: F1 Prediction Challenge

A web app for three players (Carmen, Mark, and Bottas) to predict Formula 1 race outcomes and compete for points across the 2026 season. Bottas is an AI-controlled player.

## Features

- **Predictions** — Before each race, players predict pole position, winner, 2nd, 3rd, a surprise pick, and a flop. Sprint weekends add sprint pole and sprint winner categories.
- **Scoring** — Objective predictions (pole, podium) are scored automatically against FastF1 data. Subjective picks (surprise, flop) are manually approved by an admin.
- **Standings** — Season-long leaderboard with race-by-race point breakdowns, countdown to the next race, and deadline warnings.
- **Race Detail** — Side-by-side view of predictions vs. actual results with visual correctness indicators.
- **Driver & Team Standings** — Live F1 championship standings pulled from the Ergast API.
- **BOT-tas (AI player)** — "Fill BOT-tas with AI" asks a local Ollama model for picks, given the current standings, the circuit's history, and the active grid.
- **Roster upkeep** — The driver roster refreshes from a live feed, and keeps drivers who have left the grid so past races and season totals stay intact.

## Tech Stack

- **Backend:** Flask, Gunicorn
- **Data:** FastF1 (race results), Ergast API (championship standings), Jolpica (driver roster)
- **AI:** Ollama (BOT-tas's predictions), served from a host on the LAN
- **Frontend:** Jinja2 templates, custom CSS with F1 styling

## Local Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app starts at http://localhost:5000. Set the `PORT` environment variable to override.

## Deployment

The app deploys to a remote server via `make deploy`, which copies files over SSH, sets up a Python virtualenv, and installs a systemd service.

```bash
make deploy
```

Configuration is at the top of the `Makefile`:

| Variable | Default | Description |
|----------|---------|-------------|
| `REMOTE_USER` | `pfun` | SSH user on the target server |
| `REMOTE_HOST` | `192.168.1.210` | Target server IP |
| `REMOTE_DIR` | `/opt/pfun` | Install directory |

The systemd service runs gunicorn on port 80 as the `pfun` user. See [NOTES.md](NOTES.md) for details on how privileged port binding works without root.

## Roster Updates

The driver roster is refreshed from the [Jolpica](https://api.jolpi.ca) API (the
community successor to Ergast). It is a **dry run by default** — review the diff,
then apply:

```bash
make refresh-roster                 # show what would change
make refresh-roster ARGS=--write    # apply it
```

The roster is **append-only**. A driver who has appeared this season is never
deleted, only marked `"status": "out"` — saved predictions and results reference
drivers by abbreviation, so removing one would break past races and season
totals. Drivers who are out stay selectable in the prediction form (greyed and
labelled `(out)`), but are excluded from BOT-tas's choices.

The feed only reports drivers who have **completed a session**, so it lags any
driver change announced between race weekends. Those go in
`roster_overrides.json`, which is merged over the feed:

```json
{
  "drivers": { "TSU": { "first_name": "Yuki", "last_name": "Tsunoda",
                        "nationality": "Japanese", "team": "Racing Bulls" } },
  "out": ["HAD"]
}
```

Remove an override once the feed catches up — that is, once the driver has
actually raced in the new seat.

## Data Files

| File | Description |
|------|-------------|
| `2026_f1_races.json` | Race schedule (rounds, circuits, session times, sprint flags) |
| `2026_f1_drivers.json` | Driver roster (name, team, nationality, status) — see [Roster Updates](#roster-updates) |
| `roster_overrides.json` | Manual roster corrections that win over the live feed |
| `data/predictions.json` | Player predictions per race (persisted across deploys) |
| `data/results.json` | Race results and scores (persisted across deploys) |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Port for the local dev server |
| `OLLAMA_URL` | `http://192.168.1.139:11434/api/generate` | Ollama endpoint for BOT-tas |
| `OLLAMA_MODEL` | `gemma4:e4b` | Model BOT-tas uses |
| `OLLAMA_TIMEOUT` | `120` | Budget in seconds for a whole BOT-tas request. Must stay below the gunicorn `--timeout` in `pfun.service`, or the worker is killed mid-request and the browser gets an HTML error page instead of JSON. |
