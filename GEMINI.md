# GEMINI Project Context: P-Fun

P-Fun is a Flask-based web application for a Formula 1 prediction challenge between three players (Carmen, Mark, and Bottas) for the 2026 season. Bottas is an AI-controlled player.

## Project Overview

- **Purpose:** Predict F1 race outcomes (pole, podium, surprise, flop) and track scores.
- **Tech Stack:**
  - **Backend:** Python 3, Flask, Gunicorn.
  - **Data Integration:** 
    - `fastf1`: Used for retrieving live race results (Qualifying, Sprint, Race).
    - `fastf1.ergast`: Used for retrieving F1 championship standings and historical data.
  - **Frontend:** Jinja2 templates, Vanilla CSS, minimal JavaScript (mostly for countdowns and async data fetching).
- **Architecture:** 
  - Monolithic Flask application (`app.py`).
  - Data is persisted in JSON files within the `data/` directory.
  - `fastf1_cache/` stores cached F1 session data to reduce API load and improve performance.

## Core Data Structures

- **`2026_f1_races.json`**: The 2026 race calendar, including round number, location, circuit, and session times.
- **`2026_f1_drivers.json`**: The 2026 driver roster, including abbreviations, teams, and nationalities.
- **`data/predictions.json`**: Stores player predictions for each round.
- **`data/results.json`**: Stores actual race results, subjective category approvals, and calculated scores.
- **`data/cancelled.json`**: List of cancelled race rounds.

## Building and Running

### Local Development

1. **Environment Setup:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Running the App:**
   ```bash
   python app.py
   ```
   The app defaults to `http://localhost:5000`. Use the `PORT` environment variable to change it.

### Deployment

The project uses a `Makefile` for deployment to a remote server (default: `192.168.1.210`).

- **Deploy:** `make deploy`
  - Syncs code and static assets via `rsync`.
  - Installs dependencies in a remote virtualenv.
  - Configures and restarts the `pfun` systemd service.
- **Pull Production Data:** `make pull-data`
  - Syncs the remote `data/` directory to the local machine to inspect production predictions and results.

## Development Conventions

- **Data Handling:** Use `load_json` and `save_json` helpers in `app.py` for all file-based persistence.
- **FastF1 Integration:** Always utilize the `fastf1_cache` directory.
- **Styling:** Adhere to the F1-themed aesthetics defined in `static/style.css`.
- **Predictions Deadline:** Predictions are generally expected 2 days before the race time, indicated by a warning in the UI.
- **Subjective Picks:** "Surprise" and "Flop" categories are subjective and require manual approval in the "Award" interface.

## Key Files and Directories

- `app.py`: Main application logic and routing.
- `templates/`: Jinja2 templates for all views.
- `static/`: CSS, player avatars, and track maps.
- `flags/`: PNG flag icons for driver nationalities.
- `fastf1_cache/`: Local cache for FastF1 data.
- `pfun.service`: Systemd service unit for production.
