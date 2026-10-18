"""Optional exhaustive archive/workflow audit; writes evidence to --output."""

from pathlib import Path
import sys, json, time, tempfile, os
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest

R = Path(__file__).resolve().parents[1]
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("work/accuracy-audit"))
O = parser.parse_args().output
O.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(R))
from boundary_core.analytics import load

p, s, _ = load()
raw = pd.read_csv(R / "data/match_players.csv.gz", dtype={"player_id": str})
results = []
start = time.perf_counter()
with tempfile.TemporaryDirectory() as temp, patch.dict(
    os.environ, {"BOUNDARY_RUNTIME_DIR": temp}
):
    app = AppTest.from_file(str(R / "app.py"), default_timeout=90).run()
    app.sidebar.radio[0].set_value("Player dossier").run()
    for team, rows in s.groupby("franchise_id"):
        app.sidebar.selectbox[0].set_value(team).run()
        for row in rows.itertuples():
            next(
                x
                for x in app.text_input
                if x.label == "Player name, alias or registry ID"
            ).set_value(row.cricsheet_id).run()
            expected = int(
                raw[
                    (raw.player_id == row.cricsheet_id) & (raw.competition == "IPL")
                ].runs.sum()
            )
            exists = (raw.player_id == row.cricsheet_id).any()
            error = [x.message for x in app.exception]
            observed = app.metric[0].value if app.metric else None
            ok = not error and (
                (observed == str(expected))
                if exists
                else (
                    not app.metric
                    and any("No matching archive identity" in x.value for x in app.info)
                )
            )
            results.append(
                {
                    "team": team,
                    "player": row.player_name,
                    "player_id": row.cricsheet_id,
                    "expected_IPL_archive_runs": expected,
                    "displayed_runs": observed,
                    "identity_in_archive": bool(exists),
                    "passes": ok,
                    "error": error,
                }
            )
        print(team, len(rows), "dossiers tested", flush=True)
pd.DataFrame(results).to_csv(O / "all_roster_dossiers.csv", index=False)
summary = {
    "cases": len(results),
    "passes": sum(x["passes"] for x in results),
    "failures": [x for x in results if not x["passes"]],
    "seconds": round(time.perf_counter() - start, 2),
    "scope": "All 257 supplied squad rows through the real Streamlit runner; ID selected explicitly; default IPL overview totals independently summed from the stored input CSV. Missing archive identities must show no inferred totals.",
}
(O / "all_dossiers_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
assert not summary["failures"]
