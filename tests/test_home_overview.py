"""Executive overview, truthful readiness and provider-free status checks."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import ast
import importlib.util
import json
import sys
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "agents.py").exists():
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import agent_runtime


class HomeOverviewTests(unittest.TestCase):
    def app(self, key=None):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        if key is not None:
            app.secrets["DEEPSEEK_API_KEY"] = key
        return app.run()

    def test_home_architecture_and_ready_configuration_make_no_provider_call(self):
        key = "do-not-display-this-fixture-key"
        with patch("openai.OpenAI") as client:
            app = self.app(key)
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            headings = [element.value for element in app.subheader]
            self.assertIn("Hybrid 6-Agent Architecture", headings)
            self.assertIn("Empirical Evidence First", headings)
            self.assertIn("Technology & Methodology", headings)
            self.assertIn("System Status", headings)
            roles = " ".join(element.value for element in app.markdown)
            for name in ["Player Scout", "Matchup Analyst", "Auction Analyst", "Squad Analyst", "Research Coordinator", "Evidence Reviewer"]:
                self.assertIn(name, roles)
            self.assertEqual([m.value for m in app.metric], ["6,392", "141,377", "6,618"])
            self.assertTrue(any("AI configuration ready" in item.value for item in app.success))
            table = app.dataframe[-1].value
            self.assertEqual(len(table), 5)
            self.assertTrue(table.Status.eq("Loaded").all())
            all_text = " ".join(e.value for group in [app.markdown, app.caption, app.success, app.info] for e in group)
            self.assertNotIn(key, all_text)
            self.assertIn("not verified here", all_text)
            self.assertIn("does not guarantee hallucination-free", all_text)
            client.assert_not_called()

    def test_missing_key_keeps_data_online_without_claiming_endpoint_readiness(self):
        with patch("openai.OpenAI") as client:
            app = self.app()
            self.assertFalse(app.exception)
            self.assertTrue(any("System Online" in item.value for item in app.success))
            self.assertFalse(any("AI configuration ready" in item.value for item in app.success))
            self.assertTrue(any("API key is not configured" in item.value for item in app.info))
            client.assert_not_called()

    def test_missing_sdk_is_reported_without_breaking_home(self):
        real_find_spec = importlib.util.find_spec
        def find_spec(name, *args, **kwargs):
            return None if name == "openai" else real_find_spec(name, *args, **kwargs)
        with patch("importlib.util.find_spec", side_effect=find_spec):
            app = self.app("fixture-only")
            self.assertFalse(app.exception)
            self.assertTrue(any("SDK package is not discoverable" in item.value for item in app.info))
            self.assertFalse(any("AI configuration ready" in item.value for item in app.success))

    def test_unavailable_agent_layer_has_an_accurate_status(self):
        with patch.object(agent_runtime, "load_agents", side_effect=agent_runtime.AgentRuntimeError("fixture")):
            app = self.app("fixture-only")
            self.assertFalse(app.exception)
            self.assertTrue(any("agent components are unavailable" in item.value for item in app.info))
            self.assertFalse(any("AI configuration ready" in item.value for item in app.success))

    def test_status_helper_handles_missing_data_and_configuration_without_exposing_values(self):
        tree = ast.parse((ROOT / "app.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "describe_system_status")
        namespace = {"pd": pd, "find_spec": lambda name: object(),
                     "st": SimpleNamespace(secrets={"DEEPSEEK_API_KEY": "fixture-only"})}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "status", "exec"), namespace)
        status = namespace["describe_system_status"]({"Available": pd.DataFrame({"value": [1]}), "Empty": pd.DataFrame(), "Missing": None}, True)
        self.assertFalse(status["datasets_ready"])
        self.assertEqual(status["loaded_datasets"], 1)
        self.assertNotIn("fixture-only", json.dumps(status))
        namespace["st"].secrets = {"DEEPSEEK_API_KEY": "fixture-only", "DEEPSEEK_MODEL": " "}
        status = namespace["describe_system_status"]({"Available": pd.DataFrame({"value": [1]})}, True)
        self.assertFalse(status["ai_configuration_ready"])
        class BrokenSecrets:
            def get(self, *args):
                raise RuntimeError("DO_NOT_SHOW")
        namespace["st"].secrets = BrokenSecrets()
        status = namespace["describe_system_status"]({}, True)
        self.assertFalse(status["settings_readable"])
        self.assertNotIn("DO_NOT_SHOW", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
