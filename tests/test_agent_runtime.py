"""Regressions for warm-process, colliding and partially updated agent imports."""

from pathlib import Path
import os
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "agent_runtime.py").exists():
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from agent_runtime import AgentRuntimeError, load_agents
import agent_runtime


class AgentRuntimeTests(unittest.TestCase):
    def test_conflicting_cached_agents_does_not_break_all_workspaces(self):
        unrelated = ModuleType("agents")
        with patch.dict(sys.modules, {"agents": unrelated}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            for route in ["Player Profile", "Team Matchups", "Auction Trends", "Home/Overview"]:
                app.sidebar.radio[0].set_value(route).run()
                self.assertFalse(app.exception, route)
                self.assertFalse(app.error, route)
            self.assertIs(sys.modules["agents"], unrelated)
            loaded = load_agents(ROOT)
            self.assertTrue(callable(loaded.generate_auction_report))
            self.assertEqual(Path(loaded.__file__).resolve(), ROOT / "agents.py")

    def test_changed_bytes_load_new_release_without_mutating_old_module(self):
        def source(marker):
            return 'class ScoutReportError(Exception): pass\n' + ''.join(
                f'def {name}(*args): return "{marker}"\n' for name in agent_runtime._FUNCTIONS
            )
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "agents.py"
            path.write_text(source("old"))
            stamp = path.stat().st_mtime_ns
            first = load_agents(root)
            self.assertIs(first, load_agents(root))
            path.write_text(source("new"))
            os.utime(path, ns=(stamp, stamp))
            second = load_agents(root)
            self.assertIsNot(first, second)
            self.assertEqual(first.generate_auction_report({}), "old")
            self.assertEqual(second.generate_auction_report({}), "new")

    def test_incomplete_or_missing_release_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(AgentRuntimeError):
                load_agents(root)
            (Path(root) / "agents.py").write_text("class ScoutReportError(Exception): pass\n")
            with self.assertRaises(AgentRuntimeError):
                load_agents(root)

    def test_optional_agent_failure_preserves_statistical_dashboard(self):
        with patch.object(agent_runtime, "load_agents", side_effect=AgentRuntimeError("fixture")):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            for route in ["Player Profile", "Team Matchups", "Auction Trends", "Home/Overview"]:
                app.sidebar.radio[0].set_value(route).run()
                self.assertFalse(app.exception, route)
                self.assertFalse(app.error, route)
                self.assertTrue(app.metric, route)


if __name__ == "__main__":
    unittest.main()
