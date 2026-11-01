"""Moneyball arithmetic, source joins, caching and UI integration; no paid calls."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import copy
import csv
import hashlib
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "moneyball.py").exists():
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import agents
import data_loader as dl
from moneyball import (phase_batting_metrics, aggregate_season_impact,
                       latest_auction_impact, append_phase_evidence, append_impact_evidence)


class MoneyballTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deliveries = dl.load_deliveries()
        cls.prices = dl.load_clean_auction()
        cls.links = dl.load_auction_player_links()
        cls.impact = dl.load_season_impact()

    def test_phase_boundaries_wides_noballs_byes_and_superovers(self):
        rows = pd.DataFrame({
            "delivery_id": list("abcdefghi"), "match_date": ["2026-01-01"] * 9,
            "striker_id": ["P"] * 9, "is_super_over": [0] * 8 + [1],
            "over_number_zero_based": [0, 5, 5, 6, 15, 15, 16, 19, 0],
            # Third event is a wide: does not add a faced ball. Second is a no-ball
            # counted by this source. Middle zero includes a bye: a batter dot.
            "is_ball_faced_by_batter": [1, 1, 0, 1, 1, 1, 1, 1, 1],
            "batter_runs": [0, 4, 0, 1, 0, 6, 0, 4, 6],
        })
        result = phase_batting_metrics(rows, "P")["rows"]
        self.assertEqual([(r["runs"], r["balls_faced"]) for r in result], [(4, 2), (7, 3), (4, 2)])
        self.assertEqual(result[0]["strike_rate"], 200)
        self.assertEqual(result[0]["dot_ball_percentage"], 50)
        self.assertAlmostEqual(result[1]["dot_ball_percentage"], 100 / 3)
        self.assertEqual(result[2]["strike_rate"], 200)
        absent = phase_batting_metrics(rows, "absent")["rows"]
        self.assertTrue(all(r["balls_faced"] == 0 and r["strike_rate"] is None and r["dot_ball_percentage"] is None for r in absent))
        only_middle = phase_batting_metrics(rows.loc[rows.over_number_zero_based.eq(6)], "P")["rows"]
        self.assertIsNone(only_middle[0]["strike_rate"])
        self.assertIsNone(only_middle[2]["dot_ball_percentage"])

    def test_invalid_and_duplicate_delivery_evidence_is_withheld(self):
        selected = self.deliveries.head(2).copy()
        with self.assertRaises(ValueError):
            phase_batting_metrics(pd.concat([selected, selected]), selected.iloc[0].striker_id)
        for column, value in [("is_ball_faced_by_batter", 2), ("batter_runs", -1), ("over_number_zero_based", 20)]:
            rows = selected.copy()
            rows.loc[rows.index[0], column] = value
            with self.subTest(column=column), self.assertRaises(ValueError):
                phase_batting_metrics(rows, rows.iloc[0].striker_id)

    def test_every_batter_phase_reconciles_with_independent_event_loop(self):
        expected = {}
        # An independent row loop avoids reproducing the production groupby logic.
        for row in self.deliveries.itertuples(index=False):
            if row.is_super_over:
                continue
            phase = 0 if row.over_number_zero_based <= 5 else 1 if row.over_number_zero_based <= 15 else 2
            values = expected.setdefault((row.striker_id, phase), [0, 0, 0])
            values[0] += row.batter_runs
            values[1] += row.is_ball_faced_by_batter
            values[2] += int(row.is_ball_faced_by_batter == 1 and row.batter_runs == 0)
        for pid, group in self.deliveries.groupby("striker_id"):
            result = phase_batting_metrics(group, pid)
            for index, row in enumerate(result["rows"]):
                runs, balls, dots = expected.get((pid, index), [0, 0, 0])
                self.assertEqual([row["runs"], row["balls_faced"], row["batter_dot_balls"]], [runs, balls, dots], (pid, index))
                if balls:
                    self.assertAlmostEqual(row["strike_rate"], 100 * runs / balls)
                    self.assertAlmostEqual(row["dot_ball_percentage"], 100 * dots / balls)
        kohli = phase_batting_metrics(self.deliveries, "ba607b88")
        self.assertEqual(sum(r["runs"] for r in kohli["rows"]), 9336)
        self.assertEqual(sum(r["balls_faced"] for r in kohli["rows"]), 6926)

    def test_season_totals_credit_wickets_and_exclude_superovers(self):
        regular = self.deliveries.loc[self.deliveries.is_super_over.eq(0)]
        self.assertEqual(self.impact.runs.sum(), regular.batter_runs.sum())
        wickets = dl.load_ipl_wickets()
        self.assertEqual(self.impact.wickets.sum(), len(wickets.loc[wickets.is_super_over.eq(0) & wickets.credited_to_bowler.eq(1)]))
        kohli = self.impact.loc[self.impact.player_id.eq("ba607b88") & self.impact.season_year.eq(2024)].iloc[0]
        self.assertEqual(kohli.runs, 741)
        self.assertEqual(kohli.wickets, 0)
        damaged = wickets.copy()
        damaged.loc[0, "delivery_id"] = "not-a-delivery"
        with self.assertRaises(ValueError):
            aggregate_season_impact(self.deliveries, damaged, dl.load_ipl_rosters())

    def test_latest_prices_same_season_and_all_year_scopes(self):
        for year in ["All Time", *map(str, range(2013, 2027))]:
            table, summary = latest_auction_impact(self.prices, self.links, self.impact, year)
            self.assertFalse(table.cricsheet_person_id.duplicated().any())
            if year != "All Time":
                self.assertTrue(table.season_year.eq(int(year)).all())
            exact = self.links.set_index("auction_record_id")
            prices = self.prices.set_index("auction_record_id")
            for row in table.itertuples(index=False):
                link = exact.loc[row.auction_record_id]
                self.assertEqual(link.join_method, "exact_alias")
                self.assertEqual(link.review_needed, 0)
                price = prices.loc[row.auction_record_id]
                self.assertEqual(row.price, price.winning_bid_native)
                self.assertEqual(row.winning_bid_currency, price.winning_bid_currency)
                perf = self.impact.loc[self.impact.player_id.eq(row.cricsheet_person_id) & self.impact.season_year.eq(row.season_year)]
                if perf.empty:
                    self.assertFalse(row.performance_available)
                    self.assertTrue(pd.isna(row.runs) and pd.isna(row.cost_per_run) and pd.isna(row.cost_per_wicket))
                else:
                    self.assertEqual(row.runs, perf.iloc[0].runs)
                    self.assertEqual(row.wickets, perf.iloc[0].wickets)
                    for denominator, cost in [(row.runs, row.cost_per_run), (row.wickets, row.cost_per_wicket)]:
                        if denominator:
                            self.assertAlmostEqual(cost, row.price / denominator)
                        else:
                            self.assertTrue(pd.isna(cost))
        latest, summary = latest_auction_impact(self.prices, self.links, self.impact)
        self.assertGreater(summary["excluded_uncertain_links"], 0)
        self.assertGreater(summary["missing_same_season_performance"], 0)
        self.assertEqual(latest.loc[latest.player_name.eq("Cameron Green"), "season_year"].tolist(), [2026])
        pant = latest.loc[latest.player_name.eq("Rishabh Pant")].iloc[0]
        self.assertEqual(pant.runs, 269)
        self.assertAlmostEqual(pant.cost_per_run, 270000000 / 269)

    def test_latest_uncertain_sale_not_backfilled_and_ambiguous_prices_rejected(self):
        prices = pd.DataFrame({"auction_record_id": ["a", "b"], "season_year": [2025, 2026], "player_name": ["Person", "Person"],
            "team_id": ["RCB", "RCB"], "auction_status": ["Sold", "Sold"], "winning_bid_native": [100, 200], "winning_bid_currency": ["INR", "INR"]})
        links = pd.DataFrame({"auction_record_id": ["a", "b"], "season_year": [2025, 2026], "team_id": ["RCB", "RCB"],
            "cricsheet_person_id": ["P", "P"], "join_method": ["exact_alias", "heuristic"], "join_usable": [1, 1], "review_needed": [0, 1]})
        impact = pd.DataFrame({"season_year": [2025, 2026], "player_id": ["P", "P"], "runs": [0, 50], "wickets": [0, 2]})
        latest, _ = latest_auction_impact(prices, links, impact)
        self.assertTrue(latest.empty)
        previous, _ = latest_auction_impact(prices, links, impact, "2025")
        self.assertTrue(pd.isna(previous.iloc[0].cost_per_run) and pd.isna(previous.iloc[0].cost_per_wicket))
        links.loc[1, ["join_method", "review_needed"]] = ["exact_alias", 0]
        prices.loc[1, "season_year"] = 2025
        links.loc[1, "season_year"] = 2025
        ambiguous, info = latest_auction_impact(prices, links, impact)
        self.assertTrue(ambiguous.empty)
        self.assertEqual(info["excluded_ambiguous_sales"], 2)
        for value in [0, -1, float("inf"), None]:
            bad = prices.head(1).copy()
            bad["winning_bid_native"] = value
            result, info = latest_auction_impact(bad, links.head(1), impact)
            self.assertTrue(result.empty)
            self.assertEqual(info["excluded_invalid_prices"], 1)

    def test_cache_reads_once_and_invalidates_when_source_changes(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dl, "DATA_DIR", Path(folder)):
            nested = Path(folder) / dl.CLEAN_SUBDIRECTORY
            nested.mkdir()
            path = nested / "ipl_deliveries_clean_2008_2026.csv"
            self.deliveries.head(2).to_csv(path, index=False)
            real_reader = pd.read_csv
            with patch.object(pd, "read_csv", wraps=real_reader) as reader:
                first = dl.load_deliveries()
                second = dl.load_deliveries()
                self.assertEqual(len(first), 2)
                self.assertEqual(reader.call_count, 1)
                self.deliveries.head(3).to_csv(path, index=False)
                third = dl.load_deliveries()
                self.assertEqual(reader.call_count, 2)
                self.assertEqual(len(third), 3)
                self.assertNotEqual(first.attrs["source_sha256"], third.attrs["source_sha256"])

    def test_player_and_auction_ui_packets_validate_and_stay_bounded(self):
        with patch("openai.OpenAI") as client:
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            app.sidebar.radio[0].set_value("Player Profile").run()
            app.selectbox[0].set_value("ba607b88").run()
            packet = json.loads(app.json[-1].value)
            self.assertTrue(packet["phase_batting"]["available"])
            self.assertEqual(len(packet["phase_batting"]["rows"]), 3)
            self.assertLessEqual(len(packet["facts"]), 30)
            agents._check_evidence(packet, "player_scouting")
            for row in packet["phase_batting"]["rows"]:
                self.assertIn(row["fact_ids"]["strike_rate"], {f["id"] for f in packet["facts"]})
            app.selectbox[1].set_value("T20I").run()
            self.assertFalse(json.loads(app.json[-1].value)["phase_batting"]["available"])
            app.sidebar.radio[0].set_value("Auction Trends").run()
            for year in ["All Time", *map(str, range(2013, 2027))]:
                next(s for s in app.selectbox if s.label == "Moneyball sale season").set_value(year).run()
                self.assertFalse(app.exception)
                packet = json.loads(app.json[-1].value)
                self.assertEqual(packet["moneyball"]["scope"]["selected_year"], year)
                self.assertLessEqual(len(packet["facts"]), 80)
                self.assertLessEqual(len(packet["moneyball"]["examples"]), 4)
                agents._check_evidence(packet, "auction_analysis")
                encoded = json.dumps(packet, ensure_ascii=False, allow_nan=False)
                self.assertLessEqual(len(encoded.encode()), 24000)
                self.assertNotIn('NaN', encoded)
            client.assert_not_called()

    def test_provider_receives_new_metrics_and_renders_their_citations(self):
        client = MagicMock()
        client.__enter__.return_value = client
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.secrets["DEEPSEEK_API_KEY"] = "fixture-only"
        with patch("openai.OpenAI", return_value=client):
            app.run()
            for route, button, key in [("Player Profile", "Generate Scouting Report", "phase_batting"),
                                       ("Auction Trends", "Generate Auction Report", "moneyball")]:
                app.sidebar.radio[0].set_value(route).run()
                packet = json.loads(app.json[-1].value)
                fid = packet["facts"][-1]["id"]
                report = {"observations": [{"text": "The supplied metric describes this historical sample.", "fact_ids": [fid]}],
                          "interpretations": [], "limitations": ["Historical evidence is descriptive."], "next_steps": []}
                client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
                    finish_reason="stop", message=SimpleNamespace(content="```json\n" + json.dumps(report) + "\n```", tool_calls=None))])
                next(b for b in app.button if b.label == button).click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                sent = json.loads(client.chat.completions.create.call_args.kwargs["messages"][1]["content"].split("\n", 1)[1])
                self.assertIn(key, sent)
                self.assertTrue(sent[key]["available"])
                self.assertTrue(any(f"[{fid}]" in c.value for c in app.caption))
            calls = client.chat.completions.create.call_count
            next(s for s in app.selectbox if s.label == "Moneyball sale season").set_value("2026").run()
            self.assertEqual(client.chat.completions.create.call_count, calls)
            self.assertTrue(any("different year" in item.value for item in app.info))

    def test_optional_source_failure_preserves_workspaces(self):
        from data_runtime import load_data_layer
        ui_loader = load_data_layer(ROOT).data_loader
        with patch.object(ui_loader, "load_deliveries", side_effect=FileNotFoundError("Fixture missing deliveries")), patch("openai.OpenAI") as client:
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            app.sidebar.radio[0].set_value("Player Profile").run()
            self.assertFalse(app.exception)
            self.assertTrue(app.metric)
            self.assertFalse(json.loads(app.json[-1].value)["phase_batting"]["available"])
            client.assert_not_called()
        with patch.object(ui_loader, "load_clean_auction", side_effect=FileNotFoundError("Fixture missing auction")):
            app.sidebar.radio[0].set_value("Auction Trends").run()
            self.assertFalse(app.exception)
            self.assertFalse(json.loads(app.json[-1].value)["moneyball"]["available"])

    def test_metric_source_change_changes_report_fingerprint(self):
        base = {"task": "player_scouting", "player": {"id": "ba607b88"}, "scope": {"competition": "IPL"},
                "facts": [{"id": "F1", "metric": "Runs", "value": 9336, "unit": "runs"}], "limitations": []}
        first = append_phase_evidence(copy.deepcopy(base), phase_batting_metrics(self.deliveries, "ba607b88"))
        changed = self.deliveries.loc[self.deliveries.striker_id.eq("ba607b88")].copy()
        changed.loc[changed.index[0], "batter_runs"] += 1
        second = append_phase_evidence(copy.deepcopy(base), phase_batting_metrics(changed, "ba607b88"))
        self.assertNotEqual(agents.scout_context_fingerprint(first), agents.scout_context_fingerprint(second))
        table, summary = latest_auction_impact(self.prices, self.links, self.impact)
        auction = {"task": "auction_analysis", "scope": {"selected_year": "All Time"}, "facts": base["facts"], "limitations": []}
        first = append_impact_evidence(copy.deepcopy(auction), table, summary)
        prices = self.prices.copy()
        prices.loc[0, "winning_bid_native"] += 1
        changed_table, changed_summary = latest_auction_impact(prices, self.links, self.impact)
        second = append_impact_evidence(copy.deepcopy(auction), changed_table, changed_summary)
        self.assertNotEqual(agents.auction_context_fingerprint(first), agents.auction_context_fingerprint(second))


if __name__ == "__main__":
    unittest.main()
