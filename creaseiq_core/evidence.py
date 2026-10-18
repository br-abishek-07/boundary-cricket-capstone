"""Reproducible task context and safe decision-pack exports."""

from pathlib import Path
from functools import lru_cache
import datetime, hashlib, io, json, math, zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VERSION = "3.1.0"
FILES = [
    "data/match_players.csv.gz",
    "data/matches.csv.gz",
    "data/squads.csv",
    "data/squad_events.json",
    "data/roster_status.json",
    "data/player_registry.json",
    "data/attack_types.json",
    "data/prediction_model.json",
    "creaseiq_core/analytics.py",
    "creaseiq_core/agent.py",
    "creaseiq_core/prediction.py",
    "creaseiq_core/evidence.py",
    "match_data.py",
    "app.py",
    "creaseiq_runtime.py",
]
CONTEXT_FIELDS = {
    "competition",
    "discipline",
    "phase",
    "min_balls",
    "since",
    "excluded",
    "locked",
    "costs",
    "budget",
    "min_bowlers",
    "min_batters",
    "min_spin",
    "min_pace",
    "overrides",
    "intent",
    "target_ids",
    "target_names",
    "matchup",
    "candidate_ids",
    "candidate_excluded_ids",
    "candidate_pool",
}


def safe(v):
    if isinstance(v, pd.DataFrame):
        return safe(v.to_dict("records"))
    if isinstance(v, dict):
        return {str(k): safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [safe(x) for x in v]
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if hasattr(v, "item"):
        return safe(v.item())
    return v


@lru_cache(maxsize=64)
def _file_hash(path, mtime, size):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def source_hashes():
    return {
        path: _file_hash(
            path, (ROOT / path).stat().st_mtime_ns, (ROOT / path).stat().st_size
        )
        for path in FILES
        if (ROOT / path).exists()
    }


def context_only(scenario):
    return {k: safe(v) for k, v in scenario.items() if k in CONTEXT_FIELDS}


def context_key(question, team, until, scenario):
    payload = {
        "question": question.strip(),
        "team": team,
        "until_exclusive": until,
        "context": context_only(scenario),
        "sources": source_hashes(),
        "version": VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def manifest(team, until, scenario, kind, question=""):
    return {
        "application": "CreaseIQ",
        "version": VERSION,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task": kind,
        "question": question,
        "team": team,
        "until_exclusive": until,
        "context": context_only(scenario),
        "source_sha256": source_hashes(),
        "context_fingerprint": context_key(question, team, until, scenario),
        "assumptions": [
            "Totals cover supplied match records only. Known T20I and SMAT coverage gaps prevent complete career or tournament claims.",
            "The supplied 2026 squad has partial dated verification. Confirm eligibility and current availability.",
            "Prices and capability overrides are analyst assumptions. Scores are descriptive and do not predict future value.",
            "Scouting comparisons remain separate by competition. No league-strength translation is assumed.",
            "A twenty-over plan enforces the stated scheduling rules; full Impact Player and competition certification are outside its scope.",
        ],
        "data_source": "Supplied Cricsheet archives; https://cricsheet.org/",
    }


def export_frame(frame, team, until, scenario, kind, question=""):
    df = frame.copy()
    df["evidence_team"] = team
    df["evidence_before"] = until
    df["evidence_from"] = scenario.get("since", "")
    df["scope_competition"] = scenario.get("competition", "IPL")
    df["scope_phase"] = scenario.get("phase", "All")
    df["method_version"] = VERSION
    df["task"] = kind
    df["context_fingerprint"] = context_key(question, team, until, scenario)
    return df


def decision_pack(frame, team, until, scenario, kind, question="", extras=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "manifest.json",
            json.dumps(
                manifest(team, until, scenario, kind, question),
                indent=2,
                allow_nan=False,
            ),
        )
        z.writestr(
            "results.csv",
            export_frame(frame, team, until, scenario, kind, question).to_csv(
                index=False
            ),
        )
        for name, value in (extras or {}).items():
            if Path(name).name != name:
                raise ValueError("Export entries must be simple filenames.")
            if isinstance(value, pd.DataFrame):
                z.writestr(name, value.to_csv(index=False))
            elif isinstance(value, (dict, list)):
                z.writestr(name, json.dumps(safe(value), indent=2, allow_nan=False))
            else:
                z.writestr(name, str(value))
    return buffer.getvalue()
