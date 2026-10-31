"""Squad metadata, provider contracts and UI regressions; no live API calls."""

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
    "task": "squad_analysis", "franchise": {"id": "RCB", "name": "Fixture franchise"},
    "scope": {"roster_status": "Supplied snapshot"},
    "facts": [{"id": "F1", "metric": "Listed entries", "value": 25, "unit": "source rows"}],
    "limitations": ["Current registration is unverified."], "source_fingerprint": "fixture-source",
}
REPORT = {
    "observations": [{"text": "The supplied snapshot lists squad entries.", "fact_ids": ["F1"]}],
    "interpretations": [], "limitations": ["Current registration and availability are unverified."],
    "next_steps": ["Verify the roster and role metadata before planning selection."],
}


class SquadAgentTests(unittest.TestCase):
    def setUp(self):
        secrets = patch.object(agents.st, "secrets", {"DEEPSEEK_API_KEY": "fixture-only"})
        secrets.start()
        self.addCleanup(secrets.stop)
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=json.dumps(REPORT), tool_calls=None)
        )])
        factory = patch("openai.OpenAI", return_value=self.client)
        self.factory = factory.start()
        self.addCleanup(factory.stop)

    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.secrets["DEEPSEEK_API_KEY"] = "fixture-only"
        app.run()
        app.sidebar.radio[0].set_value("Squad Analysis").run()
        self.assertFalse(app.exception)
        return app

    def test_shared_engine_prompt_fences_and_extended_limit(self):
        report = copy.deepcopy(REPORT)
        report["limitations"] *= 7
        self.client.chat.completions.create.return_value.choices[0].message.content = "```json\n" + json.dumps(report) + "\n```"
        result = agents.generate_squad_report(copy.deepcopy(PACKET))
        self.assertEqual(len(result["limitations"]), 7)
        self.assertEqual(result["_provenance"]["context_fingerprint"], agents.squad_context_fingerprint(PACKET))
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertIn("Cricket Squad Analyst", request["messages"][0]["content"])
        self.assertNotIn("tools", request)
        self.assertEqual(self.factory.call_args.kwargs["max_retries"], 0)

    def test_franchise_task_and_unknown_citations_are_checked(self):
        invalid = copy.deepcopy(PACKET)
        invalid["franchise"]["id"] = ""
        with self.assertRaises(agents.ScoutReportError):
            agents.generate_squad_report(invalid)
        with self.assertRaises(agents.ScoutReportError):
            agents.generate_auction_report(copy.deepcopy(PACKET))
        self.factory.assert_not_called()
        report = copy.deepcopy(REPORT)
        report["observations"][0]["fact_ids"] = ["F999"]
        raw = json.dumps(report)
        self.client.chat.completions.create.return_value.choices[0].message.content = raw
        with patch.object(agents.st, "error") as debug:
            with self.assertRaises(agents.ScoutReportError):
                agents.generate_squad_report(copy.deepcopy(PACKET))
            self.assertIn(raw, debug.call_args.args[0])

    def test_all_ten_franchises_counts_and_placeholder_ids(self):
        app = self.app()
        import data_loader
        source = data_loader.load_squads()
        self.assertEqual(len(app.selectbox[0].options), 10)
        for team in sorted(source.franchise_id.unique()):
            app.selectbox[0].set_value(team).run()
            self.assertFalse(app.exception, team)
            packet = json.loads(app.json[-1].value)
            rows = source.loc[source.franchise_id.eq(team)]
            self.assertEqual(packet["summary"]["listed_players"], len(rows))
            self.assertEqual(len(app.dataframe[0].value), len(rows))
            self.assertEqual(sum(row["count"] for row in packet["role_counts"]), len(rows))
            self.assertEqual({row["role"]: row["count"] for row in packet["role_counts"]}, rows.role.value_counts().to_dict())
            origins = {row["origin"]: row["count"] for row in packet["origin_counts"]}
            self.assertEqual(origins["Domestic"], int(rows.is_overseas.eq(0).sum()))
            self.assertEqual(origins["Overseas"], int(rows.is_overseas.eq(1).sum()))
            self.assertEqual(sum(origins.values()), len(rows))
            keepers = {row["flag"]: row["count"] for row in packet["wicketkeeper_flags"]}
            self.assertEqual(keepers["Yes"], int(rows.is_wicketkeeper.eq(1).sum()))
            self.assertIsNone(packet["scope"]["snapshot_date"])
            self.assertEqual(len(packet["roster"]), len(rows))
            agents._check_evidence(packet, "squad_analysis")
            if team == "RCB":
                self.assertEqual(packet["summary"]["listed_players"], 25)
                self.assertLess(rows.cricsheet_id.nunique(), 25)
        self.client.chat.completions.create.assert_not_called()

    def test_generation_cache_franchise_staleness_and_other_workspaces(self):
        app = self.app()
        click = lambda: next(b for b in app.button if b.label == "Generate Squad Report").click().run()
        self.client.chat.completions.create.assert_not_called()
        click()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        packet = json.loads(self.client.chat.completions.create.call_args.kwargs["messages"][1]["content"].split("\n", 1)[1])
        self.assertEqual(packet["franchise"]["id"], "RCB")
        self.assertEqual(packet["summary"]["listed_players"], 25)
        click()
        self.assertEqual(self.client.chat.completions.create.call_count, 1)
        app.selectbox[0].set_value("MI").run()
        self.assertTrue(any("different franchise" in m.value for m in app.info))
        self.assertFalse(any(m.value == "**Squad composition observations**" for m in app.markdown))
        click()
        self.assertFalse(app.exception)
        self.assertEqual(self.client.chat.completions.create.call_count, 2)
        for route in ["Player Profile", "Team Matchups", "Auction Trends", "Home/Overview", "Squad Analysis"]:
            app.sidebar.radio[0].set_value(route).run()
            self.assertFalse(app.exception, route)

    def test_raw_debug_preserves_squad_table(self):
        self.client.chat.completions.create.return_value.choices[0].message.content = "bad squad JSON"
        app = self.app()
        next(b for b in app.button if b.label == "Generate Squad Report").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("bad squad JSON" in m.value for m in app.error))
        self.assertEqual(app.metric[0].value, "25")

    def helpers(self):
        namespace = {"pd": pd, "json": json, "hashlib": __import__("hashlib")}
        tree = ast.parse((ROOT / "app.py").read_text())
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[]), "helpers", "exec"), namespace)
        columns = {"player": "player_name", "role": "role", "overseas": "is_overseas",
                   "keeper": "is_wicketkeeper", "nationality": "nationality",
                   "designation": "designation", "registry": "cricsheet_id"}
        return namespace, columns, ["Batter", "Bowler", "All Rounder", "Wicket Keeper"]

    def test_unknown_flags_do_not_use_nationality_and_placeholders_do_not_merge(self):
        namespace, columns, expected = self.helpers()
        rows = pd.DataFrame({
            "player_name": ["A", "B", "C", "D", "E"],
            "role": ["Batter", None, "Bowler", "Unclassified", "All Rounder"],
            "is_overseas": [0, 1, 2, None, "x"], "nationality": ["Indian"] * 5,
            "is_wicketkeeper": [1, 0, None, 2, "x"],
            "cricsheet_id": ["UNREGISTERED_DOMESTIC_SQUAD"] * 5,
        })
        original = rows.copy(deep=True)
        packet = namespace["build_squad_evidence"](rows, "T", "Team", columns, expected)
        origins = {row["origin"]: row["count"] for row in packet["origin_counts"]}
        self.assertEqual(origins, {"Domestic": 1, "Overseas": 1, "Unknown": 3})
        self.assertEqual(packet["summary"]["listed_players"], 5)
        self.assertEqual(packet["summary"]["unclassified_role_entries"], 2)
        self.assertEqual(sum(row["count"] for row in packet["role_counts"]), 5)
        self.assertTrue(any("Zero entries" in limit for limit in packet["limitations"]))
        agents._check_evidence(packet, "squad_analysis")
        pd.testing.assert_frame_equal(rows, original)

    def test_missing_metadata_and_duplicate_names_remain_explicit(self):
        namespace, columns, expected = self.helpers()
        rows = pd.DataFrame({"player_name": ["A", "A", None]})
        packet = namespace["build_squad_evidence"](rows, "T", "Team", columns, expected)
        self.assertEqual(packet["summary"]["listed_players"], 3)
        self.assertEqual(packet["summary"]["distinct_listed_names"], 1)
        self.assertEqual(packet["summary"]["duplicate_name_entries"], 1)
        self.assertEqual(packet["summary"]["missing_player_names"], 1)
        self.assertEqual(next(row["count"] for row in packet["origin_counts"] if row["origin"] == "Unknown"), 3)
        self.assertEqual(next(row["count"] for row in packet["wicketkeeper_flags"] if row["flag"] == "Unknown"), 3)
        self.assertEqual(len(packet["roster"]), 3)
        agents._check_evidence(packet, "squad_analysis")


if __name__ == "__main__":
    unittest.main()
