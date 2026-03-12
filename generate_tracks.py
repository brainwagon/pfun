#!/usr/bin/env python3
"""Generate stylized F1 racetrack PNG images using FastF1 telemetry data."""

import json
import os
import sys

import fastf1
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection

# FastF1 cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".fastf1_cache")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "tracks")
SMALL_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "small_tracks")
MEDIUM_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "medium_tracks")
RACES_FILE = os.path.join(os.path.dirname(__file__), "2026_f1_races.json")

# Map circuit names from 2026_f1_races.json to (year, FastF1 GP name) tuples.
# Madrid is new for 2026 with no historical data — maps to None.
CIRCUIT_LOOKUP = {
    "Albert Park Circuit": (2024, "Australian Grand Prix"),
    "Shanghai International Circuit": (2024, "Chinese Grand Prix"),
    "Suzuka International Racing Course": (2024, "Japanese Grand Prix"),
    "Bahrain International Circuit": (2024, "Bahrain Grand Prix"),
    "Jeddah Corniche Circuit": (2024, "Saudi Arabian Grand Prix"),
    "Miami International Autodrome": (2024, "Miami Grand Prix"),
    "Circuit Gilles Villeneuve": (2024, "Canadian Grand Prix"),
    "Circuit de Monaco": (2024, "Monaco Grand Prix"),
    "Circuit de Barcelona-Catalunya": (2024, "Spanish Grand Prix"),
    "Red Bull Ring": (2024, "Austrian Grand Prix"),
    "Silverstone Circuit": (2024, "British Grand Prix"),
    "Circuit de Spa-Francorchamps": (2024, "Belgian Grand Prix"),
    "Hungaroring": (2024, "Hungarian Grand Prix"),
    "Circuit Zandvoort": (2024, "Dutch Grand Prix"),
    "Autodromo Nazionale Monza": (2024, "Italian Grand Prix"),
    "Circuito IFEMA Madrid": None,
    "Baku City Circuit": (2024, "Azerbaijan Grand Prix"),
    "Marina Bay Street Circuit": (2024, "Singapore Grand Prix"),
    "Circuit of the Americas": (2024, "United States Grand Prix"),
    "Autodromo Hermanos Rodriguez": (2024, "Mexico City Grand Prix"),
    "Autodromo Jose Carlos Pace (Interlagos)": (2024, "São Paulo Grand Prix"),
    "Las Vegas Strip Circuit": (2024, "Las Vegas Grand Prix"),
    "Lusail International Circuit": (2024, "Qatar Grand Prix"),
    "Yas Marina Circuit": (2024, "Abu Dhabi Grand Prix"),
}

# Style constants
BG_COLOR = "#15151e"
TRACK_COLOR_START = "#38383f"
TRACK_COLOR_END = "#e10600"
TRACK_WIDTH = 6
SHADOW_WIDTH = 12
SHADOW_COLOR = "#0a0a12"
FIG_WIDTH = 10.24
FIG_HEIGHT = 7.68
DPI = 100


def get_track_data(year, gp_name):
    """Load FastF1 session and return position data and circuit info."""
    session = fastf1.get_session(year, gp_name, "R")
    session.load()

    fastest_lap = session.laps.pick_fastest()
    pos_data = fastest_lap.get_pos_data()
    circuit_info = session.get_circuit_info()

    return pos_data[["X", "Y"]], circuit_info


def process_track_coordinates(pos_data, circuit_info):
    """Rotate track coordinates and close the loop."""
    rotation = circuit_info.rotation
    rotation_rad = np.radians(rotation)

    x = pos_data["X"].values
    y = pos_data["Y"].values

    # Apply rotation
    x_rot = x * np.cos(rotation_rad) - y * np.sin(rotation_rad)
    y_rot = x * np.sin(rotation_rad) + y * np.cos(rotation_rad)

    # Close the loop
    x_rot = np.append(x_rot, x_rot[0])
    y_rot = np.append(y_rot, y_rot[0])

    return x_rot, y_rot


def render_track(x, y, circuit_info, race_name, country, output_path):
    """Render a stylized track image."""
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT), dpi=DPI)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.set_aspect("equal")
    ax.axis("off")

    # Build line segments for LineCollection
    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    # Color gradient from gray to red
    n_segments = len(segments)
    colors = np.zeros((n_segments, 4))
    start_rgb = np.array([0x38, 0x38, 0x3f]) / 255.0
    end_rgb = np.array([0xe1, 0x06, 0x00]) / 255.0
    for i in range(n_segments):
        t = i / max(n_segments - 1, 1)
        colors[i, :3] = start_rgb * (1 - t) + end_rgb * t
        colors[i, 3] = 1.0

    # Shadow line (wider, darker, behind)
    shadow_lc = LineCollection(segments, linewidths=SHADOW_WIDTH,
                               colors=SHADOW_COLOR, alpha=0.6,
                               capstyle="round", joinstyle="round")
    ax.add_collection(shadow_lc)

    # Main track line with gradient
    track_lc = LineCollection(segments, linewidths=TRACK_WIDTH,
                              colors=colors, capstyle="round",
                              joinstyle="round")
    ax.add_collection(track_lc)

    # Start/finish marker
    ax.plot(x[0], y[0], "o", color="white", markersize=8, zorder=5)

    # Corner numbers
    rotation_rad = np.radians(circuit_info.rotation)
    corners = circuit_info.corners
    for _, corner in corners.iterrows():
        cx = corner["X"] * np.cos(rotation_rad) - corner["Y"] * np.sin(rotation_rad)
        cy = corner["X"] * np.sin(rotation_rad) + corner["Y"] * np.cos(rotation_rad)

        # Find nearest track point for perpendicular offset direction
        dists = (x - cx) ** 2 + (y - cy) ** 2
        nearest_idx = np.argmin(dists)

        # Compute offset direction perpendicular to track
        if nearest_idx < len(x) - 1:
            dx = x[nearest_idx + 1] - x[nearest_idx]
            dy = y[nearest_idx + 1] - y[nearest_idx]
        else:
            dx = x[nearest_idx] - x[nearest_idx - 1]
            dy = y[nearest_idx] - y[nearest_idx - 1]
        length = np.sqrt(dx**2 + dy**2)
        if length > 0:
            # Perpendicular unit vector
            nx_dir = -dy / length
            ny_dir = dx / length
        else:
            nx_dir, ny_dir = 0, 1

        # Offset distance proportional to track extent
        extent = max(x.max() - x.min(), y.max() - y.min())
        offset = extent * 0.03

        ax.text(cx + nx_dir * offset, cy + ny_dir * offset,
                str(int(corner["Number"])),
                color="white", fontsize=7, ha="center", va="center",
                alpha=0.7, fontweight="bold")

    # Auto-scale with padding
    ax.autoscale_view()
    x_margin = (x.max() - x.min()) * 0.1
    y_margin = (y.max() - y.min()) * 0.1
    ax.set_xlim(x.min() - x_margin, x.max() + x_margin)
    ax.set_ylim(y.min() - y_margin, y.max() + y_margin)

    # Race name and country text
    fig.text(0.05, 0.92, race_name, color="white", fontsize=20,
             fontweight="bold", ha="left", va="top",
             fontfamily="sans-serif")
    fig.text(0.05, 0.87, country, color=TRACK_COLOR_END, fontsize=12,
             ha="left", va="top", fontfamily="sans-serif")

    fig.savefig(output_path, facecolor=BG_COLOR, bbox_inches=None,
                pad_inches=0, dpi=DPI)
    plt.close(fig)
    print(f"  Saved: {output_path}")


def render_placeholder(race_name, country, output_path):
    """Render a placeholder image for circuits with no data."""
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT), dpi=DPI)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")

    # "Coming Soon" text
    ax.text(0.5, 0.45, "TRACK DATA\nCOMING SOON", color="#38383f",
            fontsize=36, ha="center", va="center",
            fontweight="bold", transform=ax.transAxes,
            linespacing=1.5)

    # Race name and country
    fig.text(0.05, 0.92, race_name, color="white", fontsize=20,
             fontweight="bold", ha="left", va="top",
             fontfamily="sans-serif")
    fig.text(0.05, 0.87, country, color=TRACK_COLOR_END, fontsize=12,
             ha="left", va="top", fontfamily="sans-serif")

    fig.savefig(output_path, facecolor=BG_COLOR, bbox_inches=None,
                pad_inches=0, dpi=DPI)
    plt.close(fig)
    print(f"  Saved (placeholder): {output_path}")


SMALL_WIDTH = 1.28
SMALL_HEIGHT = 0.96
SMALL_TRACK_WIDTH = 2.5
SMALL_SHADOW_WIDTH = 5

MEDIUM_WIDTH = 2.56
MEDIUM_HEIGHT = 1.92
MEDIUM_TRACK_WIDTH = 3.5
MEDIUM_SHADOW_WIDTH = 7


def render_track_small(x, y, output_path):
    """Render a small track thumbnail with transparent background."""
    fig, ax = plt.subplots(figsize=(SMALL_WIDTH, SMALL_HEIGHT), dpi=DPI)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    ax.set_aspect("equal")
    ax.axis("off")

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    n_segments = len(segments)
    colors = np.zeros((n_segments, 4))
    start_rgb = np.array([0x38, 0x38, 0x3f]) / 255.0
    end_rgb = np.array([0xe1, 0x06, 0x00]) / 255.0
    for i in range(n_segments):
        t = i / max(n_segments - 1, 1)
        colors[i, :3] = start_rgb * (1 - t) + end_rgb * t
        colors[i, 3] = 1.0

    shadow_lc = LineCollection(segments, linewidths=SMALL_SHADOW_WIDTH,
                               colors=SHADOW_COLOR, alpha=0.6,
                               capstyle="round", joinstyle="round")
    ax.add_collection(shadow_lc)

    track_lc = LineCollection(segments, linewidths=SMALL_TRACK_WIDTH,
                              colors=colors, capstyle="round",
                              joinstyle="round")
    ax.add_collection(track_lc)

    ax.autoscale_view()
    x_margin = (x.max() - x.min()) * 0.08
    y_margin = (y.max() - y.min()) * 0.08
    ax.set_xlim(x.min() - x_margin, x.max() + x_margin)
    ax.set_ylim(y.min() - y_margin, y.max() + y_margin)

    fig.savefig(output_path, transparent=True, bbox_inches="tight",
                pad_inches=0.02, dpi=DPI)
    plt.close(fig)
    print(f"  Saved small: {output_path}")


def render_placeholder_small(output_path):
    """Render a small transparent placeholder with a subtle track outline."""
    fig, ax = plt.subplots(figsize=(SMALL_WIDTH, SMALL_HEIGHT), dpi=DPI)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    ax.axis("off")

    ax.text(0.5, 0.5, "?", color="#38383f", fontsize=24, ha="center",
            va="center", fontweight="bold", transform=ax.transAxes)

    fig.savefig(output_path, transparent=True, bbox_inches="tight",
                pad_inches=0.02, dpi=DPI)
    plt.close(fig)
    print(f"  Saved small (placeholder): {output_path}")


def render_track_medium(x, y, output_path):
    """Render a medium track thumbnail with transparent background."""
    fig, ax = plt.subplots(figsize=(MEDIUM_WIDTH, MEDIUM_HEIGHT), dpi=DPI)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    ax.set_aspect("equal")
    ax.axis("off")

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    n_segments = len(segments)
    colors = np.zeros((n_segments, 4))
    start_rgb = np.array([0x38, 0x38, 0x3f]) / 255.0
    end_rgb = np.array([0xe1, 0x06, 0x00]) / 255.0
    for i in range(n_segments):
        t = i / max(n_segments - 1, 1)
        colors[i, :3] = start_rgb * (1 - t) + end_rgb * t
        colors[i, 3] = 1.0

    shadow_lc = LineCollection(segments, linewidths=MEDIUM_SHADOW_WIDTH,
                               colors=SHADOW_COLOR, alpha=0.6,
                               capstyle="round", joinstyle="round")
    ax.add_collection(shadow_lc)

    track_lc = LineCollection(segments, linewidths=MEDIUM_TRACK_WIDTH,
                              colors=colors, capstyle="round",
                              joinstyle="round")
    ax.add_collection(track_lc)

    ax.autoscale_view()
    x_margin = (x.max() - x.min()) * 0.08
    y_margin = (y.max() - y.min()) * 0.08
    ax.set_xlim(x.min() - x_margin, x.max() + x_margin)
    ax.set_ylim(y.min() - y_margin, y.max() + y_margin)

    fig.savefig(output_path, transparent=True, bbox_inches="tight",
                pad_inches=0.02, dpi=DPI)
    plt.close(fig)
    print(f"  Saved medium: {output_path}")


def render_placeholder_medium(output_path):
    """Render a medium transparent placeholder."""
    fig, ax = plt.subplots(figsize=(MEDIUM_WIDTH, MEDIUM_HEIGHT), dpi=DPI)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    ax.axis("off")

    ax.text(0.5, 0.5, "?", color="#38383f", fontsize=36, ha="center",
            va="center", fontweight="bold", transform=ax.transAxes)

    fig.savefig(output_path, transparent=True, bbox_inches="tight",
                pad_inches=0.02, dpi=DPI)
    plt.close(fig)
    print(f"  Saved medium (placeholder): {output_path}")


def main():
    fastf1.Cache.enable_cache(CACHE_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(SMALL_OUTPUT_DIR, exist_ok=True)
    os.makedirs(MEDIUM_OUTPUT_DIR, exist_ok=True)

    with open(RACES_FILE) as f:
        races = json.load(f)

    # Optional: generate a single round
    target_round = None
    if len(sys.argv) > 1:
        target_round = int(sys.argv[1])

    for race in races:
        round_num = race["round"]
        if target_round is not None and round_num != target_round:
            continue

        race_name = race["name"]
        country = race["country"]
        location = race["location"].lower().replace(" ", "_")
        circuit = race["circuit"]
        filename = f"round_{round_num:02d}_{location}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)
        small_output_path = os.path.join(SMALL_OUTPUT_DIR, filename)
        medium_output_path = os.path.join(MEDIUM_OUTPUT_DIR, filename)

        print(f"Round {round_num}: {race_name}")

        lookup = CIRCUIT_LOOKUP.get(circuit)
        if lookup is None:
            render_placeholder(race_name, country, output_path)
            render_placeholder_small(small_output_path)
            render_placeholder_medium(medium_output_path)
            continue

        year, gp_name = lookup
        try:
            pos_data, circuit_info = get_track_data(year, gp_name)
            x, y = process_track_coordinates(pos_data, circuit_info)
            render_track(x, y, circuit_info, race_name, country, output_path)
            render_track_small(x, y, small_output_path)
            render_track_medium(x, y, medium_output_path)
        except Exception as e:
            print(f"  ERROR: {e}")
            render_placeholder(race_name, country, output_path)
            render_placeholder_small(small_output_path)
            render_placeholder_medium(medium_output_path)


if __name__ == "__main__":
    main()
