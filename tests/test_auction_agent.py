"""Auction evidence, shared agent contracts and UI; no live provider calls."""

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
    "task": "auction_analysis", "scope": {"selected_year": "2022"},
    "facts": [{"id": "F1", "metric": "Recorded amount", "value": 100, "unit": "unverified source units"}],
    "limitations": ["Currency is unverified."], "source_fingerprint": "fixture-source",
}
REPORT = {
    "observations": [{"text": "The selected source records contain recorded amounts.", "fact_ids": ["F1"]}],
    "interpretations": [], "limitations": ["Currency and transaction types are unverified."],
    "next_steps": ["Verify units and transaction definitions before comparing market values."],
}


class AuctionAgentTests(unittest.TestCase):
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
        app.sidebar.radio[0].set_value("Auction Trends").run()
        self.assertFalse(app.exception)
        return app

    def test_shared_parser_prompt_provenance_and_extended_limit(self):
        report = copy.deepcopy(REPORT)
        report["limitations"] *= 7
        self.client.chat.completions.create.return_value.choices[0].message.content = "```json\n" + json.dumps(report) + "\n```"
        result = agents.generate_auction_report(copy.deepcopy(PACKET))
        self.assertEqual(len(result["limitations"]), 7)
        self.assertEqual(result["_provenance"]["context_fingerprint"], agents.auction_context_fingerprint(PACKET))
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertIn("Cricket Auction Analyst", request["messages"][0]["content"])
        self.assertIn("maximum of five limitations", request["messages"][0]["content"])
        self.assertNotIn("tools", request)
        self.assertEqual(self.factory.call_args.kwargs["max_retries"], 0)

    def test_wrong_scope_task_and_unknown_references_are_rejected(self):
        wrong = copy.deepcopy(PACKET)
        wrong["scope"]["selected_year"] = "not a year"
        with self.assertRaises(agents.ScoutReportError):
            agents.generate_auction_report(wrong)
        with self.assertRaises(agents.ScoutReportError):
            agents.generate_matchup_report(copy.deepcopy(PACKET))
        self.factory.assert_not_called()
        invalid = copy.deepcopy(REPORT)
        invalid["observations"][0]["fact_ids"] = ["F999"]
        raw = json.dumps(invalid)
        self.client.chat.completions.create.return_value.choices[0].message.content = raw
        with patch.object(agents.st, "error") as debug:
            with self.assertRaises(agents.ScoutReportError):
                agents.generate_auction_report(copy.deepcopy(PACKET))
            self.assertIn(raw, debug.call_args.args[0])

    def test_all_year_packets_reconcile_with_dashboard_and_source(self):
        app = self.app()
        import data_loader
        raw = data_loader.load_auction()
        for year in app.selectbox[0].options:
            app.selectbox[0].set_value(year).run()
            self.assertFalse(app.exception, year)
            packet = json.loads(app.json[-1].value)
            expected = raw if year == "All Time" else raw.loc[raw.Year.eq(int(year))]
            total = int(expected.Amount.sum())
            self.assertEqual(packet["scope"]["selected_year"], year)
            self.assertEqual(packet["summary"]["source_records"], len(expected))
            self.assertEqual(packet["summary"]["total_recorded_amount"], total)
            self.assertEqual(sum(row["recorded_amount"] for row in packet["franchise_spending"]), total)
            for rows in packet["category_breakdowns"].values():
                self.assertEqual(sum(row["recorded_amount"] for row in rows), total)
            top = expected.sort_values("Amount", ascending=False, kind="stable").head(10)
            self.assertEqual([row["Recorded amount"] for row in packet["top_buys"]], top.Amount.tolist())
            self.assertLessEqual(len(packet["facts"]), 80)
            agents._check_evidence(packet, "auction_analysis")
            ids = {fact["id"] for fact in packet["facts"]}
            self.assertTrue(all(row["fact_ids"]["amount"] in ids for row in packet["top_buys"]))
            self.assertFalse(packet["scope"]["currency_verified"])
            self.assertFalse(packet["scope"]["inflation_adjusted"])
            self.assertEqual(packet["summary"]["unknown_year_records"], 1 if year == "All Time" else 0)
        self.client.chat.completions.create.assert_not_called()

    def test_ui_generation_cache_stale_year_and_existing_workspaces(self):
        app = self.app()
        click = lambda: next(b for b in app.button if b.label == "Generate Auction Report").click().run()
        self.client.chat.completions.create.assert_not_called()
        click()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        packet = json.loads(self.client.chat.completions.create.call_args.kwargs["messages"][1]["content"].split("\n", 1)[1])
        self.assertEqual(packet["scope"]["selected_year"], "All Time")
        self.assertEqual(packet["summary"]["total_recorded_amount"], 20422875000)
        click()
        self.assertEqual(self.client.chat.completions.create.call_count, 1)
        app.selectbox[0].set_value("2022").run()
        self.assertTrue(any("different year" in m.value for m in app.info))
        self.assertFalse(any(m.value == "**Historical observations**" for m in app.markdown))
        click()
        self.assertFalse(app.exception)
        self.assertEqual(self.client.chat.completions.create.call_count, 2)
        for route in ["Player Profile", "Team Matchups", "Home/Overview", "Auction Trends"]:
            app.sidebar.radio[0].set_value(route).run()
            self.assertFalse(app.exception, route)

    def test_raw_debug_preserves_dashboard(self):
        self.client.chat.completions.create.return_value.choices[0].message.content = "bad auction JSON"
        app = self.app()
        next(b for b in app.button if b.label == "Generate Auction Report").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("bad auction JSON" in m.value for m in app.error))
        self.assertEqual(app.metric[0].value, "970")

    def test_unusable_amounts_disable_requests_and_missing_categories_work(self):
        import data_loader
        raw = data_loader.load_auction()
        invalid = raw.copy()
        invalid["Amount"] = "unusable"
        with patch.object(data_loader, "load_auction", return_value=invalid):
            app = self.app()
            self.assertTrue(next(b for b in app.button if b.label == "Generate Auction Report").disabled)
            self.assertIsNone(json.loads(app.json[-1].value)["summary"]["total_recorded_amount"])
        with patch.object(data_loader, "load_auction", return_value=raw.drop(columns=["Role", "Player Origin"])):
            app = self.app()
            packet = json.loads(app.json[-1].value)
            self.assertEqual(packet["category_breakdowns"], {})
            agents._check_evidence(packet, "auction_analysis")
        self.client.chat.completions.create.assert_not_called()

    def test_zero_amounts_and_source_preservation(self):
        namespace = {"pd": pd, "json": json, "hashlib": __import__("hashlib")}
        tree = ast.parse((ROOT / "app.py").read_text())
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[]), "helpers", "exec"), namespace)
        records = namespace["prepare_auction_records"](pd.DataFrame({
            "Year": [2022, None], "Amount": [0, 0], "Player": ["A", "A"],
            "Team": ["T", None], "Role": ["Bowler", None],
        }), "Year", "Amount")
        snapshot = records.copy(deep=True)
        packet = namespace["build_auction_evidence"](records, "All Time", "Player", "Team", ["Role"], "source units")
        self.assertEqual(packet["summary"]["total_recorded_amount"], 0)
        self.assertTrue(all(row["share_percent"] is None for row in packet["franchise_spending"]))
        self.assertEqual(len(packet["top_buys"]), 2)
        self.assertEqual(packet["summary"]["unknown_year_records"], 1)
        agents._check_evidence(packet, "auction_analysis")
        pd.testing.assert_frame_equal(records, snapshot)


if __name__ == "__main__":
    unittest.main()
