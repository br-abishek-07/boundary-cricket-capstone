"""Regressions for scope, ambiguous identities and dated selection blocks."""

from pathlib import Path
import sys, unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from boundary_core.analytics import (
    load,
    resolve,
    select_window,
    squads_asof,
    roster_scores,
    optimize,
)
from boundary_core.agent import task_context, dispatch
from streamlit.testing.v1 import AppTest


class Accuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.s, _ = load()

    def test_kohli_scope_explains_small_total(self):
        kohli = self.p[self.p.player_id.eq("ba607b88")]
        self.assertEqual(
            select_window(kohli, "IPL", "2023-10-18", "2026-10-18", "Death").runs.sum(),
            114,
        )
        self.assertEqual(
            select_window(kohli, "IPL", "2023-10-18", "2026-10-18", "All").runs.sum(),
            2073,
        )
        self.assertEqual(
            select_window(kohli, "IPL", "2008-04-18", "2026-10-18", "All").runs.sum(),
            9336,
        )

    def test_question_scope_conflicts_and_valid_season(self):
        probes = [
            ("Find death bowlers excluding Jasprit Bumrah", {}),
            (
                "Show Virat Kohli IPL 2016 performance",
                {
                    "intent": "Player evidence",
                    "target_ids": ["ba607b88"],
                    "phase": "All",
                },
            ),
            ("Compare middle over bowling options", {}),
            ("Find under-25 death bowlers", {}),
            ("Compare death and powerplay bowling", {}),
            (
                "Compare RCB versus CSK",
                {
                    "intent": "Match research",
                    "matchup": {"team1": "RCB", "team2": "MI"},
                },
            ),
            ("Build the XI and lock Virat Kohli", {"intent": "XI planning"}),
            ("Find death batters", {}),
            ("Compare T20I death bowlers", {}),
            ("Build CSK XI", {"intent": "XI planning"}),
            (
                "Show Virat Kohli IPL career totals",
                {
                    "intent": "Player evidence",
                    "target_ids": ["ba607b88"],
                    "phase": "All",
                },
            ),
        ]
        for question, scenario in probes:
            with self.subTest(question=question):
                _, errors = task_context(
                    question, self.p, "RCB", "2026-10-18", scenario
                )
                self.assertTrue(errors)
        _, errors = task_context(
            "Show Virat Kohli IPL 2016 performance",
            self.p,
            "RCB",
            "2017-01-01",
            {
                "intent": "Player evidence",
                "target_ids": ["ba607b88"],
                "phase": "All",
                "since": "2016-01-01",
            },
        )
        self.assertEqual(errors, [])

    def test_matching_competition_discipline_and_franchise_remain_usable(self):
        for question, scenario in [
            ("Compare T20I death bowlers", {"competition": "T20I"}),
            ("Find death batters", {"discipline": "Batting"}),
            ("Build CSK XI", {"intent": "XI planning"}),
        ]:
            with self.subTest(question=question):
                _, errors = task_context(
                    question, self.p, "CSK", "2026-10-18", scenario
                )
                self.assertEqual(errors, [])
        _, errors = task_context(
            "Compare RCB versus CSK",
            self.p,
            "RCB",
            "2026-10-18",
            {"intent": "Match research", "matchup": {"team1": "RCB", "team2": "CSK"}},
        )
        self.assertEqual(errors, [])

    def test_confirmed_exclusion_is_not_positive_candidate(self):
        bumrah = resolve(self.p, "Jasprit Bumrah")[0]["player_id"]
        scope, errors = task_context(
            "Find death bowlers excluding Jasprit Bumrah",
            self.p,
            "MI",
            "2026-10-18",
            {"candidate_excluded_ids": [bumrah]},
        )
        self.assertFalse(errors)
        self.assertNotIn(bumrah, scope.get("candidate_ids", []))
        result = dispatch(
            "scout_players", {}, self.p, self.s, {}, "MI", "2026-10-18", scope
        )
        self.assertNotIn(bumrah, str(result))

    def test_identical_names_require_identity_but_accept_confirmed_id(self):
        self.assertEqual(len(resolve(self.p, "Rohit Sharma")), 3)
        _, errors = task_context("Compare Rohit Sharma", self.p, "MI", "2026-10-18", {})
        self.assertTrue(any("more than one" in e for e in errors))
        scope, errors = task_context(
            "Show Rohit Sharma",
            self.p,
            "MI",
            "2026-10-18",
            {"intent": "Player evidence", "target_ids": ["740742ef"]},
        )
        self.assertFalse(errors)
        self.assertEqual(scope["target_ids"], ["740742ef"])
        _, errors = task_context(
            "Show Virat Kohli",
            self.p,
            "MI",
            "2026-10-18",
            {"intent": "Player evidence", "target_ids": ["740742ef"]},
        )
        self.assertTrue(errors)

    def test_dated_status_and_no_future_roster_assumption(self):
        before = squads_asof(self.s, "2026-03-24").set_index("player_name")
        after = squads_asof(self.s, "2026-03-25").set_index("player_name")
        self.assertFalse(before.loc["Nathan Ellis", "selection_blocked"])
        self.assertTrue(before.loc["Spencer Johnson", "selection_blocked"])
        self.assertTrue(after.loc["Nathan Ellis", "selection_blocked"])
        self.assertFalse(after.loc["Spencer Johnson", "selection_blocked"])
        with self.assertRaises(ValueError):
            squads_asof(self.s, "2027-01-01")

    def test_overrides_cannot_restore_sourced_unavailability(self):
        r = roster_scores(self.p, self.s, "RCB", "2026-10-18")
        plan = optimize(
            r,
            locked=["Yash Dayal"],
            overrides={
                "Yash Dayal": {
                    "reason": "Counterfactual test",
                    "capacity": 4,
                    "pp": 4,
                    "mid": 4,
                    "death": 4,
                    "attack_type": "Pace",
                    "utility": 999,
                }
            },
        )
        self.assertFalse(plan["ok"])


class DossierInterface(unittest.TestCase):
    def test_overview_and_ambiguous_name(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
        app.sidebar.radio[0].set_value("Player dossier").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].label, "Runs in archive")
        self.assertEqual(app.metric[0].value, "9336")
        next(x for x in app.radio if x.label == "Dossier view").set_value(
            "Use active research filters"
        ).run()
        self.assertEqual(app.metric[0].label, "Runs in Death phase")
        self.assertEqual(app.metric[0].value, "114")
        self.assertTrue(any("2,073" in x.value for x in app.info))
        next(
            x for x in app.text_input if x.label == "Player name, alias or registry ID"
        ).set_value("Rohit Sharma").run()
        self.assertFalse(app.exception)
        self.assertIsNone(
            next(x for x in app.selectbox if x.label == "Confirm identity").value
        )
        self.assertEqual(len(app.metric), 0)
        next(
            x for x in app.text_input if x.label == "Player name, alias or registry ID"
        ).set_value("740742ef").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(
            next(x for x in app.selectbox if x.label == "Confirm identity").value[
                "player_id"
            ],
            "740742ef",
        )


if __name__ == "__main__":
    unittest.main()
