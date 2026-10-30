"""Cached dataset loaders for IPL Intelligence 360°."""

from pathlib import Path

import pandas as pd
import streamlit as st


# Resolve paths relative to this script, independent of the terminal directory.
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "creaseiq" / "data"
# The existing GitHub repository stores its datasets directly in data/.
if not DATA_DIR.is_dir():
    DATA_DIR = ROOT_DIR / "data"


def _dataset_path(filename: str) -> Path:
    """Return the dataset path or raise a helpful error."""
    path = DATA_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required dataset not found: {path}")
    return path


@st.cache_data(show_spinner=False)
def load_matches() -> pd.DataFrame:
    """Load match details; Pandas automatically decompresses gzip."""
    return pd.read_csv(
        _dataset_path("matches.csv.gz"),
        compression="infer",
        low_memory=False,
    )


@st.cache_data(show_spinner=False)
def load_match_players() -> pd.DataFrame:
    """Load player-by-match statistics."""
    return pd.read_csv(
        _dataset_path("match_players.csv.gz"),
        compression="infer",
        low_memory=False,
    )


@st.cache_data(show_spinner=False)
def load_squads() -> pd.DataFrame:
    """Load the supplied franchise squad pools."""
    return pd.read_csv(
        _dataset_path("squads.csv"),
        encoding="utf-8-sig",
        low_memory=False,
    )


@st.cache_data(show_spinner=False)
def load_auction() -> pd.DataFrame:
    """Load historical auction records."""
    return pd.read_csv(
        _dataset_path("auction.csv"),
        encoding="utf-8-sig",
        low_memory=False,
    )


@st.cache_data(show_spinner=False)
def load_player_registry() -> pd.DataFrame:
    """Load registry records, preserving player IDs as the index."""
    # In the supplied JSON, "people" maps IDs to existing record fields.
    document = pd.read_json(
        _dataset_path("player_registry.json"),
        typ="series",
    )
    people = document.get("people")
    if not isinstance(people, dict):
        raise ValueError(
            "player_registry.json must contain a 'people' mapping."
        )
    return pd.DataFrame.from_dict(people, orient="index")
