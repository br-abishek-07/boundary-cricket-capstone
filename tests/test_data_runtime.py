"""Warm-process imports, source changes and complete data-layer contracts."""
from pathlib import Path
import os
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "data_runtime.py").exists():
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import data_runtime
from data_runtime import DataRuntimeError, load_data_layer


class DataRuntimeTests(unittest.TestCase):
    def test_cached_old_loader_and_unrelated_moneyball_preserve_all_routes(self):
        old_loader = ModuleType("data_loader")
        unrelated_metrics = ModuleType("moneyball")
        with patch.dict(sys.modules, {"data_loader": old_loader, "moneyball": unrelated_metrics}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            for route in ["Home/Overview", "Player Profile", "Team Matchups", "Squad Analysis", "Auction Trends"]:
                app.sidebar.radio[0].set_value(route).run()
                self.assertFalse(app.exception, route)
                self.assertFalse(app.error, route)
                self.assertTrue(app.metric, route)
                if route == "Player Profile":
                    self.assertTrue(app.json)
                if route == "Auction Trends":
                    self.assertTrue(any(s.label == "Moneyball sale season" for s in app.selectbox))
            self.assertIs(sys.modules["data_loader"], old_loader)
            self.assertIs(sys.modules["moneyball"], unrelated_metrics)
            layer = load_data_layer(ROOT)
            self.assertEqual(Path(layer.data_loader.__file__).resolve(), ROOT / "data_loader.py")
            self.assertEqual(Path(layer.moneyball.__file__).resolve(), ROOT / "moneyball.py")
            self.assertIn(layer.__name__, layer.data_loader.__package__)

    def write_release(self, root, marker):
        metrics = ''.join(f'def {name}(*args): return "{marker}"\n' for name in data_runtime._METRIC_FUNCTIONS)
        loader = 'from .moneyball import aggregate_season_impact\n' + ''.join(
            f'def {name}(*args): return aggregate_season_impact()\n' for name in data_runtime._LOADER_FUNCTIONS)
        (root / "moneyball.py").write_text(metrics)
        (root / "data_loader.py").write_text(loader)

    def test_captured_source_changes_bypass_same_timestamp_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.write_release(root, "old")
            stamp = (root / "moneyball.py").stat().st_mtime_ns
            first = load_data_layer(root)
            self.assertIs(first, load_data_layer(root))
            self.write_release(root, "new")
            os.utime(root / "moneyball.py", ns=(stamp, stamp))
            second = load_data_layer(root)
            self.assertIsNot(first, second)
            self.assertEqual(first.data_loader.load_season_impact(), "old")
            self.assertEqual(second.data_loader.load_season_impact(), "new")
            self.assertEqual(first.moneyball.aggregate_season_impact(), "old")

    def test_missing_incomplete_and_broken_releases_are_rejected_and_recover(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(DataRuntimeError):
                load_data_layer(root)
            self.write_release(root, "old")
            (root / "data_loader.py").write_text('def load_matches(): return None\n')
            with self.assertRaises(DataRuntimeError):
                load_data_layer(root)
            self.write_release(root, "old")
            (root / "moneyball.py").write_text('raise ValueError("internal detail")\n')
            with self.assertRaises(DataRuntimeError) as failure:
                load_data_layer(root)
            self.assertNotIn("internal detail", str(failure.exception))
            self.write_release(root, "new")
            self.assertEqual(load_data_layer(root).data_loader.load_matches(), "new")

    def test_season_aggregation_uses_its_paired_metrics_module(self):
        layer = load_data_layer(ROOT)
        layer.data_loader._cached_season_impact.clear()
        wrong = ModuleType("moneyball")
        wrong.aggregate_season_impact = lambda *args: (_ for _ in ()).throw(AssertionError("wrong cached dependency"))
        with patch.dict(sys.modules, {"moneyball": wrong}):
            result = layer.data_loader.load_season_impact()
            self.assertGreater(len(result), 0)
            self.assertEqual(result.loc[result.player_id.eq("ba607b88"), "runs"].sum(), 9336)
            self.assertIs(sys.modules["moneyball"], wrong)

    def test_unavailable_release_has_readable_ui_without_import_traceback(self):
        with patch.object(data_runtime, "load_data_layer", side_effect=DataRuntimeError("fixture")):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("data components are updating" in item.value for item in app.error))

    def test_ui_contract_rejects_partially_updated_runtime(self):
        partial = SimpleNamespace(data_loader=SimpleNamespace(), moneyball=SimpleNamespace())
        with patch.object(data_runtime, "load_data_layer", return_value=partial):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("data components are updating" in item.value for item in app.error))


if __name__ == "__main__":
    unittest.main()
