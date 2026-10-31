"""Matchup analyst contracts and UI checks; provider calls are mocked."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import ast
import copy
import json
import sys
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "agents.py").exists():
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import agents

PACKET = {
    "task": "matchup_analysis", "teams": {"team_a": "A", "team_b": "B"},
    "scope": {"competition": "IPL", "venue": "Venue"},
    "facts": [{"id": "F1", "metric": "Encounters", "value": 3, "unit": "matches"},
              {"id": "F12", "metric": "Recent winner", "value": "A", "unit": "recorded result"}],
    "limitations": ["Coverage is incomplete."], "recent_matches": [],
    "source_fingerprint": "fixture-source",
}
REPORT = {
    "observations": [{"text": "The archive includes encounters and recorded outcomes.", "fact_ids": ["F1", "F12"]}],
    "interpretations": [], "limitations": ["The historical sample may be incomplete."],
    "next_steps": ["Review current conditions before making a tactical decision."],
}


class MatchupAgentTests(unittest.TestCase):
    def setUp(self):
        self.secret_patch = patch.object(agents.st, "secrets", {"DEEPSEEK_API_KEY": "fixture-only"})
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=json.dumps(REPORT), tool_calls=None)
        )])
        factory_patch = patch("openai.OpenAI", return_value=self.client)
        self.factory = factory_patch.start()
        self.addCleanup(factory_patch.stop)

    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.secrets["DEEPSEEK_API_KEY"] = "fixture-only"
        app.run()
        app.sidebar.radio[0].set_value("Team Matchups").run()
        self.assertFalse(app.exception)
        return app

    def test_shared_engine_uses_matchup_prompt_and_fenced_json(self):
        self.client.chat.completions.create.return_value.choices[0].message.content = "```json\n" + json.dumps(REPORT) + "\n```"
        result = agents.generate_matchup_report(copy.deepcopy(PACKET))
        self.assertEqual(result["observations"], REPORT["observations"])
        self.assertEqual(result["_provenance"]["context_fingerprint"], agents.matchup_context_fingerprint(PACKET))
        self.assertEqual(result["_provenance"]["prompt_version"], agents.MATCHUP_PROMPT_VERSION)
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertIn("Cricket Matchup Analyst", request["messages"][0]["content"])
        self.assertNotIn("tools", request)
        self.assertEqual(self.factory.call_args.kwargs["max_retries"], 0)

    def test_identity_task_and_unknown_citations_are_checked(self):
        for team_data in [{}, {"team_a": "A", "team_b": "A"}]:
            packet = copy.deepcopy(PACKET)
            packet["teams"] = team_data
            with self.assertRaises(agents.ScoutReportError):
                agents.generate_matchup_report(packet)
        with self.assertRaises(agents.ScoutReportError):
            agents.generate_player_scout_report(copy.deepcopy(PACKET))
        self.factory.assert_not_called()
        invalid = copy.deepcopy(REPORT)
        invalid["observations"][0]["fact_ids"] = ["F999"]
        raw = json.dumps(invalid)
        self.client.chat.completions.create.return_value.choices[0].message.content = raw
        with patch.object(agents.st, "error") as debug:
            with self.assertRaises(agents.ScoutReportError):
                agents.generate_matchup_report(copy.deepcopy(PACKET))
            self.assertIn(raw, debug.call_args.args[0])

    def test_packet_uses_correct_denominator_and_unresolved_results(self):
        namespace = {"pd": pd, "json": json, "hashlib": __import__("hashlib")}
        tree = ast.parse((ROOT / "app.py").read_text())
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[]), "helpers", "exec"), namespace)
        rows = pd.DataFrame({"team1": ["A", "B", "A"], "team2": ["B", "A", "B"],
                             "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
                             "venue": ["V", "V", "V"], "winner": ["A", "B", None]})
        build = namespace["build_matchup_evidence"]
        packet = build(rows, "A", "B", "IPL", "V", "winner", "date", "venue", "margin")
        self.assertEqual(packet["head_to_head"]["no_winner"], 1)
        self.assertAlmostEqual(packet["venue"]["team_a_win_percentage"], 100 / 3)
        self.assertEqual(packet["recent_matches"][0]["Winner"], "No recorded winner")
        self.assertTrue(any("margins" in limit.lower() for limit in packet["limitations"]))
        packet = build(rows, "A", "B", "IPL", "Unobserved venue", "winner", "date", "venue", "margin")
        self.assertIsNone(packet["venue"]["team_a_win_percentage"])
        packet = build(rows.drop(columns="winner"), "A", "B", "IPL", None, "winner", "date", "venue", "margin")
        self.assertIsNone(packet["head_to_head"]["a_wins"])
        agents._check_evidence(packet, "matchup_analysis")

    def test_ui_payload_cache_staleness_and_existing_workspaces(self):
        app = self.app()
        self.client.chat.completions.create.assert_not_called()
        click = lambda: next(b for b in app.button if b.label == "Generate Matchup Report").click().run()
        select = lambda label: next(s for s in app.selectbox if s.label == label)
        click()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        request = self.client.chat.completions.create.call_args.kwargs
        packet = json.loads(request["messages"][1]["content"].split("\n", 1)[1])
        self.assertEqual(packet["teams"], {"team_a": "RCB", "team_b": "CSK"})
        self.assertEqual(packet["head_to_head"]["matches"], 35)
        self.assertEqual(packet["head_to_head"]["a_wins"], 14)
        self.assertEqual(len(packet["recent_matches"]), 5)
        venue = select("Venue").value
        self.assertEqual(packet["venue"]["name"], venue)
        self.assertEqual(packet["venue"]["head_to_head"]["matches"], int(app.metric[4].value))
        click()
        self.assertEqual(self.client.chat.completions.create.call_count, 1)
        select("Venue").set_value(next(v for v in select("Venue").options if v != venue)).run()
        self.assertTrue(any("different teams, venue" in m.value for m in app.info))
        self.assertFalse(any(m.value == "**Historical observations**" for m in app.markdown))
        click()
        self.assertFalse(app.exception)
        self.assertEqual(self.client.chat.completions.create.call_count, 2)
        select("Team A").set_value("MI").run()
        self.assertTrue(any("different teams, venue" in m.value for m in app.info))
        for workspace in ["Player Profile", "Auction Trends", "Home/Overview", "Team Matchups"]:
            app.sidebar.radio[0].set_value(workspace).run()
            self.assertFalse(app.exception, workspace)

    def test_ui_raw_debug_and_statistics_survive_failure(self):
        self.client.chat.completions.create.return_value.choices[0].message.content = "invalid matchup JSON"
        app = self.app()
        next(b for b in app.button if b.label == "Generate Matchup Report").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("invalid matchup JSON" in m.value for m in app.error))
        self.assertEqual(app.metric[0].value, "35")

    def test_empty_matchup_does_not_call_provider(self):
        app = self.app()
        next(s for s in app.selectbox if s.label == "Team A").set_value("Kochi Tuskers Kerala").run()
        next(s for s in app.selectbox if s.label == "Team B").set_value("GT").run()
        self.assertFalse(app.exception)
        self.assertTrue(next(b for b in app.button if b.label == "Generate Matchup Report").disabled)
        self.client.chat.completions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
