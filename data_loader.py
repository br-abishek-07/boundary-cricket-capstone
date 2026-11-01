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


# Moneyball sources may be extracted as a folder under data/. The hosted copy
# uses lossless .csv.gz compression; an extracted .csv takes precedence.
CLEAN_SUBDIRECTORY = "IPL_CRICSHEET_VERIFIED_CLEAN_2008_2026"
DELIVERY_COLUMNS = [
    "delivery_id", "match_id", "match_date", "season_year", "is_super_over",
    "striker_id", "bowler_id", "over_number_zero_based", "batter_runs",
    "is_ball_faced_by_batter",
]
WICKET_COLUMNS = ["wicket_id", "delivery_id", "is_super_over", "credited_to_bowler"]
ROSTER_COLUMNS = ["match_id", "season_year", "player_id"]


def _clean_dataset_path(filename: str) -> Path:
    """Search supported roots without depending on the terminal directory."""
    roots = list(dict.fromkeys([DATA_DIR, ROOT_DIR / "data", ROOT_DIR / "creaseiq" / "data"]))
    for suffix in ["", ".gz"]:
        for root in roots:
            for folder in [root, root / CLEAN_SUBDIRECTORY]:
                path = folder / (filename + suffix)
                if path.is_file():
                    return path
    raise FileNotFoundError(f"Moneyball dataset not found: {filename} (or .gz) under data/ or creaseiq/data/.")


@st.cache_data(show_spinner=False, max_entries=8)
def _read_clean_csv(path: str, file_version: tuple, columns: tuple | None) -> pd.DataFrame:
    """Cache parsed data by path, size and nanosecond mtime, not just filename.

    Projecting required columns keeps ball-by-ball memory use modest. Values
    and event rows are not altered. File hashes support report provenance.
    """
    import hashlib
    source = Path(path)
    frame = pd.read_csv(source, usecols=list(columns) if columns else None,
                        compression="infer", encoding="utf-8-sig", low_memory=False,
                        dtype={"delivery_id": "string", "striker_id": "string", "bowler_id": "string",
                               "player_id": "string", "cricsheet_person_id": "string"})
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    frame.attrs.update(source_file=source.name, source_sha256=digest.hexdigest())
    return frame


def _load_clean_csv(filename, columns=None):
    path = _clean_dataset_path(filename)
    stat = path.stat()
    return _read_clean_csv(str(path.resolve()), (stat.st_size, stat.st_mtime_ns),
                           tuple(columns) if columns else None)


def load_deliveries() -> pd.DataFrame:
    """Cached IPL deliveries; preserve Cricsheet person IDs and ball-faced flags."""
    return _load_clean_csv("ipl_deliveries_clean_2008_2026.csv", DELIVERY_COLUMNS)


def load_clean_auction() -> pd.DataFrame:
    """Cached sold transactions with explicit native currencies and season labels."""
    return _load_clean_csv("ipl_auction_clean_2013_2026.csv")


def load_auction_player_links() -> pd.DataFrame:
    """Cached identity crosswalk; callers must reject heuristic/reviewed links."""
    return _load_clean_csv("ipl_auction_player_links.csv")


def load_ipl_wickets() -> pd.DataFrame:
    """Cached dismissal events, including the bowler-credit flag."""
    return _load_clean_csv("ipl_wickets_clean_2008_2026.csv", WICKET_COLUMNS)


def load_ipl_rosters() -> pd.DataFrame:
    """Cached observed participation; absence from a season is not zero output."""
    return _load_clean_csv("ipl_match_rosters.csv", ROSTER_COLUMNS)


@st.cache_data(show_spinner=False, max_entries=2)
def _cached_season_impact(source_versions: tuple) -> pd.DataFrame:
    """Cache groupby work by file versions; avoid hashing large frames on reruns."""
    from moneyball import aggregate_season_impact
    return aggregate_season_impact(load_deliveries(), load_ipl_wickets(), load_ipl_rosters())


def load_season_impact() -> pd.DataFrame:
    """Recalculate player-season impact only when an underlying file changes."""
    names = ["ipl_deliveries_clean_2008_2026.csv", "ipl_wickets_clean_2008_2026.csv", "ipl_match_rosters.csv"]
    versions = []
    for name in names:
        path = _clean_dataset_path(name)
        stat = path.stat()
        versions.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns))
    return _cached_season_impact(tuple(versions))
