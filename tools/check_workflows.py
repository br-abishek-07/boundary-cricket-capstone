"""Optional exhaustive archive/workflow audit; writes evidence to --output."""

from pathlib import Path
from collections import defaultdict
from unittest.mock import patch
import json, sys, time, os, tempfile, hashlib
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[1]
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("work/accuracy-audit"))
O = parser.parse_args().output
O.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(R))
from creaseiq_core.analytics import (
    load,
    scout,
    roster_scores,
    optimize,
    resolve,
    select_window,
    squads_asof,
)
from creaseiq_core import agent, storage

p, s, a = load()
model = json.loads((R / "data/prediction_model.json").read_text())
start = time.perf_counter()
result = {}
registry = json.loads((R / "data/player_registry.json").read_text())["people"]
raw = pd.read_csv(
    R / "data/match_players.csv.gz",
    dtype={"player_id": str, "match_id": str, "season": str},
)
identity = raw[["player_id", "player"]].drop_duplicates()
result["identities"] = {
    "players": p.player_id.nunique(),
    "player_match_rows": len(p),
    "all_raw_ids_in_registry": set(raw.player_id) <= set(registry),
    "raw_alias_missing": [],
    "display_name_mismatch_count": int(
        (p.player != p.player_id.map({k: v["name"] for k, v in registry.items()})).sum()
    ),
    "duplicate_rows": int(p.duplicated(["match_id", "player_id"]).sum()),
}
for row in identity.itertuples():
    if (
        row.player not in registry[row.player_id]["aliases"]
        and row.player != registry[row.player_id]["name"]
    ):
        result["identities"]["raw_alias_missing"].append(
            {"id": row.player_id, "name": row.player}
        )
by = raw.groupby(["competition", "season", "player_id"]).sum(numeric_only=True)
result["all_player_season_phase_checks"] = {
    "groups": len(by),
    "numeric_comparisons": 0,
    "mismatches": 0,
}
for name, suffix in [
    ("runs", "runs"),
    ("balls", "balls"),
    ("wickets", "wickets"),
    ("legal_balls", "legal"),
    ("conceded", "conceded"),
    ("dismissals", "dismissals"),
]:
    expected = by[[ph + "_" + suffix for ph in ["pp", "mid", "death"]]].sum(axis=1)
    result["all_player_season_phase_checks"]["numeric_comparisons"] += len(by)
    result["all_player_season_phase_checks"]["mismatches"] += int(
        (by[name] != expected).sum()
    )
scopes = []
for cutoff in ["2024-01-01", "2025-01-01", "2026-10-18"]:
    for comp in ["IPL", "BBL", "SMAT", "Hundred", "T20I", "ALL"]:
        for phase in ["All", "Powerplay", "Middle", "Death"]:
            for discipline in ["Batting", "Bowling"]:
                q = scout(p, comp, "2021-01-01", 60, discipline, cutoff, phase)
                sample = "balls" if discipline == "Batting" else "legal_balls"
                rate = "strike_rate" if discipline == "Batting" else "economy"
                ok = bool(
                    (q[sample] >= 60).all()
                    and np.isfinite(q.score).all()
                    and np.isfinite(q[rate]).all()
                    and not q.duplicated(
                        ["player_id"] + (["competition"] if comp == "ALL" else [])
                    ).any()
                )
                scopes.append(
                    {
                        "cutoff": cutoff,
                        "competition": comp,
                        "phase": phase,
                        "discipline": discipline,
                        "players": len(q),
                        "ok": ok,
                    }
                )
result["scouting_scopes"] = {
    "cases": len(scopes),
    "failures": [v for v in scopes if not v["ok"]],
}
pd.DataFrame(scopes).to_csv(O / "scouting_scopes.csv", index=False)
print("All-player and 144 scouting scope checks completed", flush=True)
missions = []
forced = []
rosters = []


def verify(x, scenario):
    if not x["ok"]:
        return []
    d = x["players"]
    z = x["schedule"].sort_values("over")
    errors = []
    if len(d) != 11 or d.cricsheet_id.duplicated().any():
        errors.append("distinct XI")
    if d.is_overseas.sum() > 4 or d.is_wicketkeeper.sum() < 1:
        errors.append("overseas / keeper")
    if z.over.tolist() != list(range(1, 21)) or z.legal_balls.sum() != 120:
        errors.append("20 overs / 120 balls")
    if z.player_id.eq(z.player_id.shift()).any():
        errors.append("consecutive overs")
    if set(z.player_id) - set(d.cricsheet_id):
        errors.append("unselected bowler")
    if set(scenario.get("excluded", [])) & set(d.player_name):
        errors.append("excluded selected")
    if set(scenario.get("locked", [])) - set(d.player_name):
        errors.append("lock omitted")
    for row in d.itertuples():
        one = z[z.player_id == row.cricsheet_id]
        if len(one) > min(4, row.bowling_capacity):
            errors.append("total cap " + row.player_name)
        for ph, col in [("Powerplay", "pp"), ("Middle", "mid"), ("Death", "death")]:
            if len(one[one.phase == ph]) > getattr(row, col + "_capacity"):
                errors.append("phase cap " + row.player_name)
    if scenario.get("budget") is not None and x["cost"] > scenario["budget"] + 1e-6:
        errors.append("budget")
    return errors


for team in sorted(s.franchise_id.unique()):
    t0 = time.perf_counter()
    r = roster_scores(p, s, team)
    base = optimize(r, min_spin=1, min_pace=2)
    assert base["ok"]
    lead = base["schedule"].bowler.value_counts().index[0]
    names = r.player_name.tolist()
    costs = {name: 1 + i % 7 * 0.5 for i, name in enumerate(names)}
    rosters.append(
        {
            "team": team,
            "pool_players": len(r),
            "pool_overseas": int(r.is_overseas.sum()),
            "missing_IPL_evidence": int(r.evidence_missing.sum()),
            "over_25_pool": len(r) > 25,
            "over_8_overseas_pool": r.is_overseas.sum() > 8,
        }
    )
    cases = [
        ("Default", {"min_spin": 1, "min_pace": 2}),
        ("Leading bowler excluded", {"excluded": [lead], "min_spin": 1, "min_pace": 2}),
        ("Two spin three pace", {"min_spin": 2, "min_pace": 3}),
        ("Budget25", {"costs": costs, "budget": 25}),
        ("Impossible budget", {"costs": costs, "budget": 0}),
        ("All excluded", {"excluded": names}),
        ("Conflicting lock", {"excluded": [lead], "locked": [lead]}),
        ("Reordered pool", {}),
        (
            "All overseas locked",
            {"locked": r[r.is_overseas.astype(bool)].player_name.head(5).tolist()},
        ),
    ]
    for label, scenario in cases:
        rr = r.sample(frac=1, random_state=42) if label == "Reordered pool" else r
        at = time.perf_counter()
        x = optimize(rr, **scenario)
        errors = verify(x, scenario)
        if (
            label
            in [
                "Impossible budget",
                "All excluded",
                "Conflicting lock",
                "All overseas locked",
            ]
            and x["ok"]
        ):
            errors.append("impossible case accepted")
        missions.append(
            {
                "team": team,
                "case": label,
                "ok": x["ok"],
                "errors": errors,
                "reason": x.get("reason"),
                "seconds": round(time.perf_counter() - at, 4),
            }
        )
    for name in names:
        x = optimize(r, locked=[name])
        forced.append(
            {
                "team": team,
                "player": name,
                "ok": x["ok"],
                "errors": verify(x, {"locked": [name]}),
                "reason": x.get("reason"),
            }
        )
    print(
        team,
        "scenarios and",
        len(names),
        "player-lock cases checked in",
        round(time.perf_counter() - t0, 2),
        "s",
        flush=True,
    )
result["team_scenarios"] = {
    "cases": len(missions),
    "failures": [v for v in missions if v["errors"]],
    "supported": sum(v["ok"] for v in missions),
}
result["all_roster_player_locks"] = {
    "cases": len(forced),
    "supported": sum(v["ok"] for v in forced),
    "failures": [v for v in forced if v["errors"]],
}
result["roster_pool_checks"] = rosters
pd.DataFrame(missions).to_csv(O / "team_scenarios.csv", index=False)
pd.DataFrame(forced).to_csv(O / "all_roster_player_locks.csv", index=False)
with tempfile.TemporaryDirectory() as temp, patch.dict(
    os.environ, {"CREASEIQ_RUNTIME_DIR": temp}
):
    owner = storage.scope("audit", "RCB")
    faults = []
    cases = [
        (
            "Scouting exclusion",
            "Find death bowlers excluding Jasprit Bumrah",
            {
                "intent": "Scouting",
                "competition": "IPL",
                "discipline": "Bowling",
                "phase": "Death",
                "min_balls": 120,
            },
        ),
        (
            "Historical season",
            "Show Virat Kohli IPL 2016 performance",
            {
                "intent": "Player evidence",
                "target_ids": [resolve(p, "Virat Kohli")[0]["player_id"]],
                "phase": "All",
            },
        ),
        (
            "Middle phase",
            "Compare middle over bowling options",
            {"intent": "Scouting", "phase": "Death"},
        ),
        (
            "Under25",
            "Find under-25 death bowlers",
            {"intent": "Scouting", "phase": "Death"},
        ),
        (
            "Wrong match",
            "Compare RCB versus CSK",
            {
                "intent": "Match research",
                "matchup": {
                    "team1": "RCB",
                    "team2": "MI",
                    "chasing": None,
                    "venue": "",
                },
            },
        ),
        (
            "Two phases",
            "Compare death and powerplay bowling",
            {"intent": "Scouting", "phase": "Death"},
        ),
        (
            "Correct phase guard",
            "Compare powerplay bowling",
            {"intent": "Scouting", "phase": "Death"},
        ),
        ("Wrong discipline", "Find death batters", {"intent": "Scouting"}),
        ("Wrong competition", "Compare T20I death bowlers", {"intent": "Scouting"}),
        ("Wrong XI franchise", "Build CSK XI", {"intent": "XI planning"}),
        (
            "Uncertified career",
            "Show Virat Kohli IPL career totals",
            {"intent": "Player evidence", "target_ids": ["ba607b88"], "phase": "All"},
        ),
    ]
    for label, question, scenario in cases:
        try:
            x = agent.prepare(
                question, p, s, model, "RCB", "2026-10-18", owner, scenario
            )
            faults.append(
                {
                    "case": label,
                    "question": question,
                    "status": x["status"],
                    "context": x["scenario"],
                    "facts": [
                        (f["record"].get("player"), f["kind"])
                        for f in x["facts"].values()
                    ],
                    "text": x["text"][:1400],
                    "should_clarify": True,
                    "passes": x["status"] == "clarification",
                }
            )
        except Exception as e:
            faults.append({"case": label, "error": str(e), "passes": False})
    result["question_alignment_probes"] = faults
result["seconds"] = round(time.perf_counter() - start, 2)
(O / "corrected_deep_checks.json").write_text(json.dumps(agent.safe(result), indent=2))
print(
    json.dumps(
        agent.safe(
            {k: v for k, v in result.items() if k not in ["question_alignment_probes"]}
        ),
        indent=2,
    )
)
print("Question probes", [(x["case"], x.get("status"), x["passes"]) for x in faults])
