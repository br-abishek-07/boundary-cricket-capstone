"""Release regression suite. Provider fixtures never spend API credit."""

import json, os, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from boundary_core.analytics import (
    load,
    scout,
    roster_scores,
    optimize,
    resolve,
    squads_asof,
    player_interval,
    select_window,
)
from boundary_core.prediction import chronology, predict, metrics, venue_key
from match_data import build, overs_to_balls
from boundary_core.agent import ask, dispatch, safe, prepare, task_context
from boundary_core import storage, downloads
from boundary_core.evidence import context_key, decision_pack, export_frame
import io


class Release(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.s, cls.a = load()
        cls.model = json.loads((ROOT / "data/prediction_model.json").read_text())
        cls.report = json.loads((ROOT / "data/prediction_report.json").read_text())
        cls.m = pd.read_csv(
            ROOT / "data/matches.csv.gz",
            dtype={"match_id": str, "season": str},
            keep_default_na=False,
        )
        cls.owner = storage.scope("test-session", "RCB")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"BOUNDARY_RUNTIME_DIR": self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_01_unique_and_counts(self):
        self.assertEqual(len(self.m), 6392)
        self.assertEqual(len(self.p), 141377)
        self.assertFalse(self.m.match_id.duplicated().any())
        self.assertFalse(self.p.duplicated(["match_id", "player_id"]).any())
        self.assertNotIn("1473495", set(self.m.match_id))
        self.assertTrue(
            (
                self.p[
                    [
                        "runs",
                        "balls",
                        "wickets",
                        "legal_balls",
                        "dismissals",
                        "conceded",
                    ]
                ]
                >= 0
            )
            .all()
            .all()
        )

    def test_02_phase_reconciliation(self):
        for target, suffix in [
            ("runs", "runs"),
            ("balls", "balls"),
            ("legal_balls", "legal"),
            ("conceded", "conceded"),
            ("wickets", "wickets"),
            ("dismissals", "dismissals"),
        ]:
            with self.subTest(metric=target):
                self.assertTrue(
                    (
                        self.p[target]
                        == self.p[
                            [ph + "_" + suffix for ph in ["pp", "mid", "death"]]
                        ].sum(axis=1)
                    ).all()
                )

    def test_03_reduced_chase(self):
        z = self.p[
            (self.p.match_id == "1082648") & (self.p.team == "Kolkata Knight Riders")
        ]
        self.assertGreater(z.balls.sum(), z.pp_balls.sum())
        self.assertGreater(z.death_balls.sum(), 0)

    def test_04_over_ball_notation(self):
        self.assertEqual(overs_to_balls(10.3), 63)
        self.assertEqual(overs_to_balls(10.3, 5), 53)
        with self.assertRaises(ValueError):
            overs_to_balls(10.6)

    def test_05_identity_aliases(self):
        for query, pid in [
            ("T Natarajan", "ce794613"),
            ("Devdutt Padikkal", "2c25d4f5"),
            ("Ayush Mhatre", "b2b4f545"),
            ("Ayush Matre", "b2b4f545"),
            ("Varun Chakaravarthy", "5b7ab5a9"),
            ("Syed Khaleel Ahmed", "a2f46292"),
            ("Rasikh Salam Dar", "b8527c3d"),
        ]:
            with self.subTest(query=query):
                self.assertEqual(resolve(self.p, query)[0]["player_id"], pid)
        self.assertFalse(self.s.cricsheet_id.duplicated().any())
        self.assertEqual(len(self.s[self.s.player_name == "Naman Tiwari"]), 1)
        self.assertEqual(resolve(self.p, "Nobody XYZ"), [])
        self.assertGreater(len(resolve(self.p, "Sharma")), 1)

    def test_06_dated_trades_and_historical_guard(self):
        with self.assertRaises(ValueError):
            squads_asof(self.s, "2025-12-31")
        before = squads_asof(self.s, "2026-10-14")
        after = squads_asof(self.s, "2026-10-15")
        self.assertEqual(
            before[before.player_name == "T Natarajan"].franchise_id.iloc[0], "DC"
        )
        self.assertEqual(
            after[after.player_name == "T Natarajan"].franchise_id.iloc[0], "SRH"
        )

    def test_07_cutoff_invariance(self):
        z = scout(self.p, since="2023-01-01", until="2025-01-01")
        pd.testing.assert_frame_equal(
            z,
            scout(
                self.p[self.p.date < "2025-01-01"],
                since="2023-01-01",
                until="2025-01-01",
            ),
        )

    def test_08_phase_filter_and_samples(self):
        r = scout(self.p, min_balls=100, discipline="Bowling", phase="Death")
        self.assertTrue((r.legal_balls >= 100).all())
        self.assertFalse(r.player_id.duplicated().any())
        self.assertTrue(np.isfinite(r.score).all())

    def test_09_competitions_separate(self):
        all_ = scout(self.p, "ALL", min_balls=120)
        self.assertIn("competition", all_)
        self.assertFalse(all_.duplicated(["competition", "player_id"]).any())
        for comp in all_.competition.unique():
            one = scout(self.p, comp, min_balls=120).set_index("player_id")
            g = all_[all_.competition == comp].set_index("player_id")
            pd.testing.assert_series_equal(g.score.sort_index(), one.score.sort_index())

    def test_10_interval_same_scope(self):
        pid = resolve(self.p, "Virat Kohli")[0]["player_id"]
        a = player_interval(
            self.p, pid, "Batting", "2026-10-18", "2024-01-01", "IPL", "Powerplay"
        )
        z = select_window(self.p, "IPL", "2024-01-01", "2026-10-18", "Powerplay")
        z = z[z.player_id == pid]
        self.assertAlmostEqual(a["rate"], 100 * z.runs.sum() / z.balls.sum())
        self.assertEqual(
            a,
            player_interval(
                self.p, pid, "Batting", "2026-10-18", "2024-01-01", "IPL", "Powerplay"
            ),
        )

    def test_11_all_ten_workload_plans(self):
        for team in sorted(self.s.franchise_id.unique()):
            with self.subTest(team=team):
                result = optimize(
                    roster_scores(self.p, self.s, team), min_spin=1, min_pace=2
                )
                self.assertTrue(result["ok"], result)
                r = result["players"]
                self.assertEqual(len(r), 11)
                self.assertLessEqual(result["overseas"], 4)
                self.assertGreaterEqual(result["keepers"], 1)
                self.assertFalse(r.evidence_missing.any())
                cols = [
                    "pp_allocated_balls",
                    "mid_allocated_balls",
                    "death_allocated_balls",
                ]
                self.assertEqual(r[cols].sum().tolist(), [36, 60, 24])
                self.assertTrue((r[cols].sum(axis=1) <= 24).all())
                self.assertTrue(
                    (r[r.bowling_capacity == 0][cols].sum(axis=1) == 0).all()
                )
                self.check_schedule(result)
                self.assertGreaterEqual(
                    len(r[(r.attack_type == "Spin") & (r.bowling_capacity > 0)]), 1
                )

    def test_12_availability_and_locks(self):
        roster = roster_scores(self.p, self.s, "RCB")
        first = optimize(roster)["players"].iloc[0].player_name
        result = optimize(roster, excluded=[first])
        self.assertTrue(result["ok"])
        self.assertNotIn(first, result["players"].player_name.tolist())
        self.assertFalse(optimize(roster, excluded=[first], locked=[first])["ok"])
        self.assertFalse(optimize(roster, excluded=roster.player_name.tolist())["ok"])

    def test_13_budget_validation(self):
        r = roster_scores(self.p, self.s, "MI")
        costs = {n: 1 for n in r.player_name}
        self.assertTrue(optimize(r, costs=costs, budget=11)["ok"])
        self.assertFalse(optimize(r, costs=costs, budget=10)["ok"])
        self.assertFalse(optimize(r, costs={}, budget=20)["ok"])
        costs[r.player_name.iloc[0]] = float("nan")
        self.assertFalse(optimize(r, costs=costs, budget=20)["ok"])

    def test_14_override_validation(self):
        r = roster_scores(self.p, self.s, "RCB")
        n = r.player_name.iloc[0]
        for o in [
            {"capacity": 4},
            {"capacity": 4, "reason": "analyst", "pp": -1},
            {"capacity": 4, "reason": "analyst", "death": float("nan")},
        ]:
            self.assertFalse(optimize(r, overrides={n: o})["ok"])

    def test_15_prediction_gate_and_symmetry(self):
        self.assertFalse(self.model["gate_passed"])
        self.assertGreaterEqual(
            self.report["test"]["post"]["brier"],
            self.report["test"]["training_chase_baseline"]["brier"],
        )
        a = predict(self.model, "RCB", "CSK", "Unknown", "RCB")
        b = predict(self.model, "CSK", "RCB", "Unknown", "RCB")
        self.assertEqual(a["pre"], 0.5)
        self.assertAlmostEqual(a["post"] + b["post"], 1)
        self.assertEqual(metrics([0, 1], [0.5, 0.5])["brier"], 0.25)

    def test_16_venue_aliases(self):
        self.assertEqual(
            venue_key("M Chinnaswamy Stadium, Bengaluru"),
            venue_key("M.Chinnaswamy Stadium"),
        )
        self.assertEqual(
            venue_key("Feroz Shah Kotla"), venue_key("Arun Jaitley Stadium, Delhi")
        )

    def test_17_forecast_future_invariance(self):
        records, _ = chronology(self.m)
        past, _ = chronology(self.m[self.m.date < "2025-01-01"])
        self.assertEqual([r for r in records if r["date"] < "2025-01-01"], past)

    def test_18_tool_filters_and_allowlist(self):
        for name, args in [
            ("execute_code", {}),
            ("scout_players", {"min_balls": "120"}),
            ("optimize_xi", {"budget": 999}),
        ]:
            with self.assertRaises(ValueError):
                dispatch(name, args, self.p, self.s, self.model, "MI", "2026-10-18", {})
        self.assertEqual(
            dispatch(
                "match_prediction",
                {},
                self.p,
                self.s,
                self.model,
                "MI",
                "2010-01-01",
                {},
            )["kind"],
            "insufficient",
        )

    def test_19_agent_dossier_phase_scope(self):
        context = {"since": "2024-01-01", "phase": "Powerplay", "competition": "IPL"}
        r = dispatch(
            "player_dossier",
            {"name": "Virat Kohli"},
            self.p,
            self.s,
            self.model,
            "RCB",
            "2026-10-18",
            context,
        )
        z = select_window(self.p, "IPL", "2024-01-01", "2026-10-18", "Powerplay")
        z = z[z.player_id == resolve(self.p, "Virat Kohli")[0]["player_id"]]
        self.assertEqual(r["records"][0]["runs"], int(z.runs.sum()))

    def test_20_agent_inherits_exact_scenario(self):
        scenario = {
            "excluded": ["A"],
            "locked": ["B"],
            "budget": 11,
            "costs": {"A": 1},
            "min_spin": 2,
            "min_pace": 3,
            "overrides": {},
        }
        with patch(
            "boundary_core.agent.optimize", return_value={"ok": False, "reason": "test"}
        ) as opt:
            dispatch(
                "optimize_xi",
                {},
                self.p,
                self.s,
                self.model,
                "MI",
                "2026-10-18",
                scenario,
            )
            self.assertEqual(opt.call_args.kwargs, scenario)

    def check_schedule(self, result):
        schedule = result["schedule"].sort_values("over")
        players = result["players"].set_index("cricsheet_id")
        self.assertEqual(schedule.over.tolist(), list(range(1, 21)))
        self.assertFalse(schedule.player_id.eq(schedule.player_id.shift()).any())
        self.assertEqual(schedule.legal_balls.sum(), 120)
        for pid, z in schedule.groupby("player_id"):
            self.assertIn(pid, players.index)
            self.assertLessEqual(len(z), min(4, players.loc[pid, "bowling_capacity"]))
            for phase, prefix in [
                ("Powerplay", "pp"),
                ("Middle", "mid"),
                ("Death", "death"),
            ]:
                self.assertLessEqual(
                    len(z[z.phase == phase]), players.loc[pid, prefix + "_capacity"]
                )

    def live(self, replies, question="Compare death bowling evidence", scenario=None):
        with patch("boundary_core.agent.provider", side_effect=replies) as mock:
            r = ask(
                question,
                self.p,
                self.s,
                self.model,
                "RCB",
                "2026-10-18",
                "fixture-key",
                self.owner,
                scenario or {},
            )
            return r, mock

    def test_21_exact_context_cache(self):
        r, m = self.live(
            [({"content": '{"selected_fact_ids":["F1"],"next_actions":["video"]}'}, {})]
        )
        self.assertEqual(r["status"], "evidence_checked")
        self.assertEqual(len(r["facts"]), 1)
        with patch("boundary_core.agent.provider") as mock:
            b = ask(
                "Compare death bowling evidence",
                self.p,
                self.s,
                self.model,
                "RCB",
                "2026-10-18",
                "fixture-key",
                self.owner,
                {},
            )
            self.assertTrue(b["cached"])
            mock.assert_not_called()

    def test_22_wrong_player_rejected_before_model(self):
        kohli = resolve(self.p, "Virat Kohli")[0]["player_id"]
        with patch("boundary_core.agent.provider") as mock:
            b = ask(
                "Show Jasprit Bumrah evidence",
                self.p,
                self.s,
                self.model,
                "RCB",
                "2026-10-18",
                "fixture-key",
                self.owner,
                {"intent": "Player evidence", "target_ids": [kohli], "phase": "All"},
            )
            self.assertEqual(b["status"], "clarification")
            mock.assert_not_called()

    def test_23_unknown_fact_falls_back(self):
        r, m = self.live(
            [({"content": '{"selected_fact_ids":["F999"],"next_actions":[]}'}, {})] * 2
        )
        self.assertTrue(r["model_selection_fallback"])
        self.assertEqual(len(r["facts"]), 8)
        self.assertNotIn("F999", r["text"])
        self.assertEqual(m.call_count, 2)

    def test_24_model_cannot_omit_xi_players(self):
        r, m = self.live(
            [({"content": '{"selected_fact_ids":["F1"],"next_actions":[]}'}, {})] * 2,
            question="Build the confirmed XI",
            scenario={"intent": "XI planning", "min_spin": 1, "min_pace": 2},
        )
        self.assertEqual(len(r["facts"]), 11)
        self.assertTrue(r["model_selection_fallback"])
        self.assertEqual(len(r["trace"][0]["result"]["schedule"]), 20)

    def test_25_model_prose_or_tools_never_rendered(self):
        for msg in [
            {"content": "invent 999 runs"},
            {"tool_calls": [{"function": {"name": "execute_code"}}]},
            "invalid",
        ]:
            with self.subTest(msg=msg):
                r, _ = self.live(
                    [(msg, {})] * 2, question="Compare evidence " + str(msg)
                )
                self.assertTrue(r["facts"])
                self.assertNotIn("999 runs", r["text"])
                self.assertTrue(r["model_selection_fallback"])

    def test_26_provider_outage_keeps_checked_local_evidence(self):
        with patch("boundary_core.agent.provider", side_effect=RuntimeError("offline")):
            r = ask(
                "Outage scenario",
                self.p,
                self.s,
                self.model,
                "RCB",
                "2026-10-18",
                "fixture-key",
                self.owner,
            )
            self.assertEqual(r["status"], "evidence_checked")
            self.assertTrue(r["model_selection_fallback"])
            self.assertIn("Local evidence", r["mode"])

    def test_27_session_team_isolation(self):
        storage.save(self.owner, "briefs", "private", {"team": "RCB"})
        storage.cache(self.owner, "key", {"example": True})
        for other in [
            storage.scope("second", "RCB"),
            storage.scope("test-session", "MI"),
        ]:
            self.assertEqual(storage.records(other), [])
            self.assertIsNone(storage.cached(other, "key"))
        with self.assertRaises(ValueError):
            storage.records("")

    def test_28_atomic_allowance(self):
        for _ in range(2):
            storage.reserve_call(self.owner, global_limit=3, session_limit=2)
        with self.assertRaises(RuntimeError):
            storage.reserve_call(self.owner, global_limit=3, session_limit=2)
        storage.reserve_call(
            storage.scope("second", "MI"), global_limit=3, session_limit=2
        )
        with self.assertRaises(RuntimeError):
            storage.reserve_call(
                storage.scope("third", "CSK"), global_limit=3, session_limit=2
            )

    def test_29_no_filter_override(self):
        scope = {
            "intent": "Scouting",
            "competition": "IPL",
            "phase": "Death",
            "discipline": "Bowling",
            "min_balls": 120,
        }
        for args in [{"min_balls": 1}, {"competition": "T20I"}, {"phase": "Powerplay"}]:
            with self.assertRaises(ValueError):
                dispatch(
                    "scout_players",
                    args,
                    self.p,
                    self.s,
                    self.model,
                    "RCB",
                    "2026-10-18",
                    scope,
                )

    def test_30_phase_conflict_needs_clarification(self):
        r = prepare(
            "Compare powerplay bowlers",
            self.p,
            self.s,
            self.model,
            "RCB",
            "2026-10-18",
            self.owner,
            {"phase": "Death"},
        )
        self.assertEqual(r["status"], "clarification")
        self.assertFalse(r["facts"])

    def test_31_safe_serialization(self):
        self.assertEqual(
            json.dumps(safe({"x": float("nan")}), allow_nan=False),
            ' {"x": null}'.strip(),
        )

    def test_32_context_fingerprint_covers_assumptions(self):
        base = {"phase": "Death", "min_balls": 120}
        k = context_key("q", "RCB", "2026-10-18", base)
        for field, value in [
            ("phase", "Powerplay"),
            ("min_balls", 1),
            ("excluded", ["Virat Kohli"]),
            ("locked", ["Virat Kohli"]),
            ("budget", 11),
            ("costs", {"Virat Kohli": 2}),
            ("overrides", {"Virat Kohli": {"capacity": 1}}),
            ("intent", "XI planning"),
        ]:
            self.assertNotEqual(
                k, context_key("q", "RCB", "2026-10-18", {**base, field: value})
            )

    def test_33_export_context_and_hashes(self):
        scope = {
            "phase": "Death",
            "since": "2023-10-18",
            "excluded": ["Example"],
            "budget": 11,
            "costs": {"Example": 1},
        }
        b = decision_pack(
            pd.DataFrame({"player": ["Example"]}),
            "RCB",
            "2026-10-18",
            scope,
            "Scouting",
            "q",
        )
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            m = json.loads(z.read("manifest.json"))
            r = pd.read_csv(z.open("results.csv"))
            self.assertEqual(m["context"], scope)
            self.assertTrue(m["source_sha256"])
            self.assertEqual(r.context_fingerprint.iloc[0], m["context_fingerprint"])
            self.assertEqual(r.evidence_before.iloc[0], "2026-10-18")

    def test_34_source_zip_is_safe_and_complete(self):
        with zipfile.ZipFile(io.BytesIO(downloads.source_zip())) as z:
            names = z.namelist()
            self.assertIn("boundary/app.py", names)
            self.assertIn("boundary/data/player_registry.json", names)
            self.assertIn("boundary/.streamlit/secrets.example.toml", names)
            self.assertFalse(
                any(
                    "secrets.toml" in n
                    or ".runtime" in n
                    or ".sqlite" in n
                    or ".env" in n
                    for n in names
                )
            )

    def test_35_unknown_override_is_applied(self):
        roster = roster_scores(self.p, self.s, "RCB")
        n = roster[
            (roster.attack_type == "Pace") & (roster.bowling_capacity > 0)
        ].player_name.iloc[0]
        x = optimize(
            roster,
            locked=[n],
            overrides={
                n: {
                    "reason": "Unverified style for this scenario",
                    "capacity": 4,
                    "pp": 4,
                    "mid": 4,
                    "death": 4,
                    "attack_type": "Unknown",
                }
            },
        )
        self.assertTrue(x["ok"])
        self.assertEqual(
            x["players"].set_index("player_name").loc[n, "attack_type"], "Unknown"
        )
        self.check_schedule(x)

    def test_36_question_exclusion_and_price_agreement(self):
        r = prepare(
            "Plan MI without Jasprit Bumrah",
            self.p,
            self.s,
            self.model,
            "MI",
            "2026-10-18",
            self.owner,
            {"intent": "XI planning"},
        )
        self.assertEqual(r["status"], "clarification")
        r = prepare(
            "Build XI under 20 crore",
            self.p,
            self.s,
            self.model,
            "MI",
            "2026-10-18",
            self.owner,
            {"intent": "XI planning", "budget": 11},
        )
        self.assertEqual(r["status"], "clarification")

    def test_37_dossier_cannot_switch_identity(self):
        scope = {
            "intent": "Player evidence",
            "target_ids": [resolve(self.p, "Jasprit Bumrah")[0]["player_id"]],
        }
        with self.assertRaises(ValueError):
            dispatch(
                "player_dossier",
                {"name": "Virat Kohli"},
                self.p,
                self.s,
                self.model,
                "MI",
                "2026-10-18",
                scope,
            )

    def test_38_holdout_contains_target_and_provenance(self):
        h = pd.read_csv(ROOT / "data/prediction_holdout.csv")
        self.assertEqual(len(h), 288)
        for c in [
            "team1",
            "team2",
            "winner",
            "chasing",
            "prediction_target",
            "model_version",
            "trained_before",
            "training_chase_baseline",
        ]:
            self.assertIn(c, h)

    def test_39_scouting_study_is_dated_and_review_unrated(self):
        b = pd.read_csv(ROOT / "data/scouting_benchmark.csv")
        self.assertEqual(len(b), 48)
        self.assertTrue((b.training_before < b.test_year.add(1).astype(str)).all())
        self.assertTrue(
            (b.with_followup_sample + b.without_followup_sample == b.selected).all()
        )
        tasks = json.loads((ROOT / "data/review_tasks.json").read_text())
        self.assertEqual(len(tasks), 20)
        self.assertTrue(all(x["reviewer_rating"] is None for x in tasks))

    def test_40_empty_or_ambiguous_identity(self):
        self.assertEqual(resolve(self.p, "---"), [])
        self.assertGreater(len(resolve(self.p, "Sharma")), 1)

    def test_41_many_team_scenarios(self):
        counts = {"supported": 0, "rejected": 0}
        for team in sorted(self.s.franchise_id.unique()):
            roster = roster_scores(self.p, self.s, team)
            default = optimize(roster, min_spin=1, min_pace=2)
            self.assertTrue(default["ok"])
            lead = default["schedule"].bowler.value_counts().index[0]
            chosen = default["players"].player_name.tolist()
            alternative = (
                default["alternatives"]
                .query("not evidence_missing")
                .player_name.iloc[0]
            )
            costs = {n: 1 for n in roster.player_name}
            scenarios = [
                {},
                {"excluded": [lead]},
                {"locked": [chosen[0]]},
                {"locked": [alternative]},
                {"costs": costs, "budget": 11},
                {"costs": costs, "budget": 10},
                {"excluded": roster.player_name.tolist()},
                {"excluded": [lead], "locked": [lead]},
                {"min_spin": 2},
                {"min_pace": 3},
            ]
            for i, scenario in enumerate(scenarios):
                with self.subTest(team=team, scenario=i):
                    x = optimize(roster, **scenario)
                    if x["ok"]:
                        counts["supported"] += 1
                        self.check_schedule(x)
                        self.assertFalse(
                            set(scenario.get("excluded", []))
                            & set(x["players"].player_name)
                        )
                        self.assertTrue(
                            set(scenario.get("locked", []))
                            <= set(x["players"].player_name)
                        )
                    else:
                        counts["rejected"] += 1
                        self.assertTrue(x["reason"])
                    if i in [5, 6, 7]:
                        self.assertFalse(x["ok"])
        self.assertEqual(sum(counts.values()), 100)
        (Path(os.environ["BOUNDARY_RUNTIME_DIR"]) / "scenario-counts.json").write_text(
            json.dumps(counts)
        )

    def test_42_concurrent_quota_limit(self):
        from concurrent.futures import ThreadPoolExecutor

        def attempt(i):
            try:
                storage.reserve_call(
                    storage.scope("concurrent-" + str(i), "ALL"),
                    global_limit=9,
                    session_limit=6,
                )
                return True
            except RuntimeError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(attempt, range(20)))
        self.assertEqual(sum(accepted), 9)
        self.assertEqual(storage.usage(self.owner)["installation_requests"], 9)

    def test_43_delivery_fixture(self):
        sample = {
            "info": {
                "gender": "male",
                "overs": 6,
                "dates": ["2020-01-01"],
                "season": 2020,
                "teams": ["A", "B"],
                "players": {"A": ["Batter"], "B": ["Bowler"]},
                "registry": {"people": {"Batter": "bat", "Bowler": "bowl"}},
            },
            "innings": [
                {
                    "team": "A",
                    "target": {"overs": 6},
                    "powerplays": [{"from": 0.1, "to": 0.2}],
                    "overs": [
                        {
                            "over": 0,
                            "deliveries": [
                                {
                                    "batter": "Batter",
                                    "bowler": "Bowler",
                                    "runs": {"batter": 0, "total": 1},
                                    "extras": {"wides": 1},
                                },
                                {
                                    "batter": "Batter",
                                    "bowler": "Bowler",
                                    "runs": {"batter": 4, "total": 5},
                                    "extras": {"noballs": 1},
                                },
                                {
                                    "batter": "Batter",
                                    "bowler": "Bowler",
                                    "runs": {"batter": 0, "total": 0},
                                    "wickets": [
                                        {"kind": "run out", "player_out": "Batter"}
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        folder = Path(self.temp.name)
        source = folder / "raw"
        source.mkdir()
        with zipfile.ZipFile(source / "ipl_json.zip", "w") as archive:
            archive.writestr("123.json", json.dumps(sample))
            archive.writestr("1473495.json", json.dumps(sample))
        build(source, folder / "processed")
        frame = pd.read_csv(folder / "processed/match_players.csv.gz").set_index(
            "player_id"
        )
        self.assertEqual(frame.loc["bat", "balls"], 2)
        self.assertEqual(frame.loc["bowl", "legal_balls"], 1)
        self.assertEqual(frame.loc["bowl", "conceded"], 6)
        self.assertEqual(frame.loc["bowl", "wickets"], 0)
        self.assertEqual(frame.loc["bat", "dismissals"], 1)
        self.assertEqual(frame.loc["bat", "pp_balls"], 1)
        self.assertEqual(frame.loc["bat", "mid_balls"], 1)

    def test_44_provider_fallback_not_cached(self):
        with patch("boundary_core.agent.provider", side_effect=RuntimeError("offline")):
            r = ask(
                "Retryable outage",
                self.p,
                self.s,
                self.model,
                "RCB",
                "2026-10-18",
                "fixture-key",
                self.owner,
            )
            self.assertTrue(r["model_selection_fallback"])
        with storage.db() as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM cache").fetchone()[0], 0
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
