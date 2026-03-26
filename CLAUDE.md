# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

P-Fun is a two-player F1 prediction challenge web app where Carmen and Mark predict race outcomes (pole position, podium, surprise/flop picks) and compete for points across the 2026 F1 season. Predictions are scored automatically via FastF1 data for objective categories, and manually approved by an admin for subjective ones.

## Tech Stack

- **Backend**: Flask (Python), single-file app (`app.py`, ~620 lines)
- **Data**: JSON files in `data/` (no database) — predictions.json, results.json, cancelled.json
- **Frontend**: Jinja2 templates, vanilla CSS/JS, F1 theme (Racing Sans One font)
- **External APIs**: FastF1 (race results/telemetry), Ergast API (championship standings)
- **Deployment**: Gunicorn on systemd, deployed via SSH/rsync to 192.168.1.210

## Common Commands

```bash
# Run locally
python app.py                  # Starts Flask dev server on port 5000

# Deploy to remote server
make deploy

# Pull live data (predictions/results) from remote
make pull-data

# Generate track visualizations from FastF1 telemetry
python generate_tracks.py
```

## Architecture

**app.py** is the entire backend — routes, data helpers, scoring logic, FastF1 integration. Key concepts:

- **Prediction categories**: pole, 2nd, 3rd, winner (objective, auto-scored); surprise, flop (subjective, admin-approved); sprint_pole, sprint_winner (sprint weekends only)
- **Scoring**: 1 point per correct prediction. Objective picks are compared against FastF1 results; subjective picks require admin toggle in the award form.
- **Data flow**: Predictions saved per race round and player → Admin fetches actual results via FastF1 → Results compared and scored → Totals shown on index page.
- **Race schedule**: `2026_f1_races.json` defines rounds, circuits, sprint flags, and UTC race times.
- **Driver roster**: `2026_f1_drivers.json` lists all drivers with abbreviations and teams.

**Key routes**: `/` (standings), `/predict/<round>` (submit picks), `/award/<round>` (admin: enter results), `/race/<round>` (detail view), `/standings` (championship tables).

**Templates** extend `base.html` which provides nav and footer. The award form has a two-step flow: input results → preview comparison → save.

## Deployment Notes

- Data files (`data/*.json`) are preserved across deploys — only copied if missing on remote.
- The systemd service (`pfun.service`) runs Gunicorn on port 80 with `CAP_NET_BIND_SERVICE`.
- FastF1 cache is synced to remote to avoid re-fetching telemetry data.
- Ergast standings fall back to 2025 data if 2026 isn't available yet.
- `TEAM_ICON_MAP` in app.py maps Ergast team names to local icon filenames (e.g., Sauber → Audi).
