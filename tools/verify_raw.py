"""Independent archive reader; does not import application ingestion or analytics code."""

from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal
import argparse, hashlib, json, time, zipfile
import pandas as pd, numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
R = Path(__file__).resolve().parents[1]
start = time.perf_counter()
if not args.source.is_dir():
    parser.error("Source archive directory does not exist.")
p = pd.read_csv(
    R / "data/match_players.csv.gz", dtype={"match_id": str, "player_id": str}
)
m = pd.read_csv(
    R / "data/matches.csv.gz", dtype={"match_id": str}, keep_default_na=False
).set_index("match_id")
fields = ["runs", "balls", "conceded", "legal_balls", "wickets", "dismissals"] + [
    f"{ph}_{metric}"
    for ph in ["pp", "mid", "death"]
    for metric in ["runs", "balls", "conceded", "legal", "wickets", "dismissals"]
]
processed = {
    key: vals
    for key, vals in zip(zip(p.match_id, p.player_id), p[fields].to_numpy(int))
}
manifest = {
    x["file"]: x["sha256"]
    for x in json.loads((R / "data/audit.json").read_text())["sources"]
}
allowed = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
dismissed = allowed | {
    "run out",
    "obstructing the field",
    "retired out",
    "hit the ball twice",
}
comps = {"ipl": "IPL", "bbl": "BBL", "sma": "SMAT", "hnd": "Hundred", "t20s": "T20I"}
checks = Counter()
seen = set()
keys = set()
bad = []
phase_flags = Counter()
sources = []
bad_matches = []


def loc(x):
    a, _, b = str(x).partition(".")
    return int(a), int(b or 0)


for archive in sorted(args.source.rglob("*_json.zip")):
    prefix = archive.stem.split("_")[0]
    if prefix not in comps:
        continue
    comp = comps[prefix]
    source = {
        "file": archive.name,
        "sha256_matches": hashlib.sha256(archive.read_bytes()).hexdigest()
        == manifest[archive.name],
    }
    included = 0
    with zipfile.ZipFile(archive) as z:
        for file in z.namelist():
            if not file.endswith(".json"):
                continue
            d = json.loads(z.read(file))
            info = d["info"]
            mid = Path(file).stem
            if info.get("gender") != "male" or mid == "1473495" or mid in seen:
                continue
            seen.add(mid)
            included += 1
            ids = info.get("registry", {}).get("people", {})
            ref = defaultdict(Counter)
            for names in info.get("players", {}).values():
                for name in names:
                    ref[ids.get(name, comp + ":" + name)]
            if (
                mid not in m.index
                or str(info["dates"][0]) != m.loc[mid, "date"]
                or comp != m.loc[mid, "competition"]
            ):
                bad_matches.append(mid)
            for inn in d.get("innings", []):
                if inn.get("super_over"):
                    continue
                bpo = 5 if comp == "Hundred" else 6
                overs = Decimal(
                    str(inn.get("target", {}).get("overs", info.get("overs", 20)))
                )
                whole, balls = loc(overs)
                planned = whole * bpo + balls
                late = planned - max(6, int(Decimal(planned) / 5 + Decimal(".5")))
                power = inn.get("powerplays", [])
                phase_flags["metadata_innings" if power else "fallback_innings"] += 1
                if overs < Decimal(str(info.get("overs", 20))):
                    phase_flags["reduced_target_innings"] += 1
                intervals = [(loc(x["from"]), loc(x["to"])) for x in power]
                for over in inn.get("overs", []):
                    legal_so_far = over["over"] * bpo
                    for position, ball in enumerate(over["deliveries"], 1):
                        address = (over["over"], position)
                        is_pp = (
                            any(a <= address <= b for a, b in intervals)
                            if intervals
                            else over["over"]
                            < (5 if comp == "Hundred" else min(6, round(planned / 20)))
                        )
                        phase = (
                            "pp"
                            if is_pp
                            else ("death" if legal_so_far >= late else "mid")
                        )
                        e = ball.get("extras", {})
                        batter = ids.get(ball["batter"], comp + ":" + ball["batter"])
                        bowler = ids.get(ball["bowler"], comp + ":" + ball["bowler"])
                        faced = 0 if "wides" in e else 1
                        legal = 0 if {"wides", "noballs"} & e.keys() else 1
                        bat_runs = int(ball["runs"]["batter"])
                        charge = bat_runs + e.get("wides", 0) + e.get("noballs", 0)
                        for person, pairs in [
                            (
                                batter,
                                {
                                    "runs": bat_runs,
                                    "balls": faced,
                                    phase + "_runs": bat_runs,
                                    phase + "_balls": faced,
                                },
                            ),
                            (
                                bowler,
                                {
                                    "conceded": charge,
                                    "legal_balls": legal,
                                    phase + "_conceded": charge,
                                    phase + "_legal": legal,
                                },
                            ),
                        ]:
                            ref[person].update(pairs)
                        for wicket in ball.get("wickets", []):
                            kind = wicket["kind"]
                            if kind in allowed:
                                ref[bowler].update(
                                    {"wickets": 1, phase + "_wickets": 1}
                                )
                            if kind in dismissed:
                                ref[
                                    ids.get(
                                        wicket["player_out"],
                                        comp + ":" + wicket["player_out"],
                                    )
                                ].update({"dismissals": 1, phase + "_dismissals": 1})
                        legal_so_far += legal
                        checks["deliveries"] += 1
            for pid, counters in ref.items():
                key = (mid, pid)
                keys.add(key)
                if key not in processed:
                    bad.append({"missing": key})
                    continue
                actual = processed[key]
                expected = np.array([counters[k] for k in fields])
                diff = np.flatnonzero(actual != expected)
                checks["field_comparisons"] += len(fields)
                for j in diff:
                    bad.append(
                        {
                            "match": mid,
                            "player": pid,
                            "field": fields[j],
                            "raw": int(expected[j]),
                            "app": int(actual[j]),
                        }
                    )
    source["included"] = included
    sources.append(source)
report = {
    "version": "Boundary 3.0.2",
    "sources": sources,
    "matches": len(seen),
    "player_matches": len(keys),
    "counts": dict(checks),
    "mismatches": len(bad),
    "examples": bad[:30],
    "all_mismatches": bad,
    "extra_player_rows": len(set(processed) - keys),
    "match_id_sets_equal": set(m.index) == seen,
    "date_or_competition_mismatches": bad_matches,
    "phase_metadata_coverage": dict(phase_flags),
    "seconds": round(time.perf_counter() - start, 2),
    "scope": "Full supplied archive reconciliation; target overs interpreted as cricket over.ball notation, not decimal overs. Fallback and analytical death labels are not proof of official field restrictions or source authenticity.",
}
destination = args.output or R / "data/raw_reconciliation.json"
destination.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
raise SystemExit(
    0
    if len(sources) == 5
    and all(x["sha256_matches"] for x in sources)
    and not bad
    and not bad_matches
    and not report["extra_player_rows"]
    and report["match_id_sets_equal"]
    else 1
)
