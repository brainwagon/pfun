# P-Fun: F1 Prediction Challenge

A web app for three players (Carmen, Mark, and Bottas) to predict Formula 1 race outcomes and compete for points across the 2026 season. Bottas is an AI-controlled player.

## Features

- **Predictions** — Before each race, players predict pole position, winner, 2nd, 3rd, a surprise pick, and a flop. Sprint weekends add sprint pole and sprint winner categories.
- **Scoring** — Objective predictions (pole, podium) are scored automatically against FastF1 data. Subjective picks (surprise, flop) are manually approved by an admin.
- **Standings** — Season-long leaderboard with race-by-race point breakdowns, countdown to the next race, and deadline warnings.
- **Race Detail** — Side-by-side view of predictions vs. actual results with visual correctness indicators.
- **Driver & Team Standings** — Live F1 championship standings pulled from the Ergast API.

## Tech Stack

- **Backend:** Flask, Gunicorn
- **Data:** FastF1 (race results), Ergast API (championship standings)
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

## Data Files

| File | Description |
|------|-------------|
| `2026_f1_races.json` | Race schedule (rounds, circuits, dates, sprint flags) |
| `2026_f1_drivers.json` | Driver roster (name, team, nationality) |
| `data/predictions.json` | Player predictions per race (persisted across deploys) |
| `data/results.json` | Race results and scores (persisted across deploys) |
