"""Analyst workflow acceptance with Streamlit's real script runner."""

from pathlib import Path
import json, os, sys, tempfile, unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Interface(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"BOUNDARY_RUNTIME_DIR": self.temp.name})
        self.env.start()
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
        self.ok()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def ok(self):
        self.assertFalse(self.app.exception, [x.message for x in self.app.exception])

    def page(self, name):
        self.app.sidebar.radio[0].set_value(name).run()
        self.ok()

    def button(self, label):
        return next(x for x in self.app.button if x.label == label)

    def test_01_home_and_presets(self):
        self.assertEqual(self.app.sidebar.radio[0].value, "Home")
        self.button("Load MI scenario").click().run()
        self.ok()
        self.assertEqual(self.app.sidebar.selectbox[0].value, "MI")
        self.assertEqual(
            self.app.session_state["scenarios"]["MI"]["excluded"], ["Jasprit Bumrah"]
        )
        self.assertEqual(
            self.app.session_state["decision_inputs"]["MI"]["intent"], "XI planning"
        )
        self.assertNotIn("brief", self.app.session_state)
        self.button("Prepare brief").click().run()
        self.ok()
        self.assertEqual(self.app.session_state["brief"]["status"], "evidence_checked")
        self.assertEqual(len(self.app.session_state["brief"]["facts"]), 11)
        self.assertNotIn(
            "Jasprit Bumrah",
            [
                x["record"]["player"]
                for x in self.app.session_state["brief"]["facts"].values()
            ],
        )

    def test_02_all_team_workspaces_and_themes(self):
        pages = [
            "Home",
            "Decision desk",
            "Scouting & comparison",
            "Squad & auction scenarios",
            "Player dossier",
            "Match research",
            "Decision journal",
            "Evaluation & sources",
            "Project guide",
            "Settings",
        ]
        for team in ["CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RCB", "RR", "SRH"]:
            self.app.sidebar.selectbox[0].set_value(team).run()
            self.ok()
            for page in pages:
                with self.subTest(team=team, page=page):
                    self.page(page)
            for theme in ["Light", "Dark"]:
                self.app.sidebar.segmented_control[0].set_value(theme).run()
                self.ok()
                self.assertEqual(self.app.session_state["appearance"], theme)

    def test_03_stale_brief_hidden_after_filter_change(self):
        self.page("Decision desk")
        self.button("Prepare brief").click().run()
        self.ok()
        self.assertEqual(self.app.session_state["brief"]["status"], "evidence_checked")
        self.assertTrue(any(x.label == "Save private brief" for x in self.app.button))
        next(x for x in self.app.selectbox if x.label == "Phase").set_value(
            "Powerplay"
        ).run()
        self.ok()
        self.assertTrue(any("Context changed" in x.value for x in self.app.warning))
        self.assertFalse(any(x.label == "Save private brief" for x in self.app.button))

    def test_04_stale_after_scenario_and_question(self):
        self.page("Decision desk")
        self.button("Prepare brief").click().run()
        self.ok()
        self.page("Squad & auction scenarios")
        next(
            x for x in self.app.multiselect if x.label == "Unavailable / exclude"
        ).set_value(["Virat Kohli"]).run()
        self.ok()
        self.page("Decision desk")
        self.assertTrue(any("Context changed" in x.value for x in self.app.warning))
        next(x for x in self.app.text_area if x.label == "Decision question").set_value(
            "A new research question"
        ).run()
        self.button("Prepare brief").click().run()
        self.ok()
        self.assertEqual(
            self.app.session_state["brief"]["question"], "A new research question"
        )

    def test_05_private_journal_and_review(self):
        self.page("Decision desk")
        self.button("Prepare brief").click().run()
        self.button("Save private brief").click().run()
        self.ok()
        self.page("Decision journal")
        self.assertEqual(len(self.app.expander), 1)
        self.app.sidebar.selectbox[0].set_value("MI").run()
        self.ok()
        self.assertEqual(len(self.app.expander), 0)
        self.page("Evaluation & sources")
        next(x for x in self.app.text_input if x.label == "Reviewer alias").set_value(
            "Test reviewer"
        )
        next(
            x for x in self.app.text_area if x.label == "Decision and evidence reviewed"
        ).set_value("MI-XI full over assignment")
        self.button("Save private review").click().run()
        self.ok()
        self.assertTrue(any("Saved privately" in x.value for x in self.app.success))

    def test_06_historical_cutoff_safe(self):
        import datetime

        self.page("Scouting & comparison")
        self.app.sidebar.date_input[0].set_value(datetime.date(2020, 1, 1)).run()
        self.ok()
        self.assertLess(self.app.session_state["filters"]["since"], "2020-01-01")
        self.page("Squad & auction scenarios")
        self.assertTrue(any("2026 snapshot" in x.value for x in self.app.warning))
        self.page("Match research")
        self.assertTrue(any("snapshot is after" in x.value for x in self.app.info))

    def test_07_multiple_capability_assumptions(self):
        self.page("Squad & auction scenarios")
        next(
            x for x in self.app.checkbox if x.label == "Capability assumptions"
        ).check().run()
        self.ok()
        players = next(
            x for x in self.app.selectbox if x.label == "Override player"
        ).options
        for name in players[:2]:
            next(x for x in self.app.selectbox if x.label == "Override player").select(
                name
            )
            next(
                x for x in self.app.text_input if x.label == "Justification / source"
            ).set_value("Tested scenario assumption")
            self.button("Add or update assumption").click().run()
            self.ok()
        self.assertEqual(
            len(self.app.session_state["scenarios"]["RCB"]["overrides"]), 2
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
