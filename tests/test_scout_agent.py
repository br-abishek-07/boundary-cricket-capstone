"""Provider-boundary and Streamlit regression checks; no live API calls."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import copy
import builtins
import importlib.util
import json
import sys
import unittest

import httpx
from openai import APITimeoutError, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "agents.py").exists():
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import agents


PACKET = {
    "task": "player_scouting", "player": {"id": "fixture-id", "name": "Fixture player"},
    "scope": {"competition": "IPL"},
    "facts": [{"id": "F1", "metric": "Runs", "value": 20, "unit": "runs"}],
    "recent_matches": [], "limitations": ["Coverage is incomplete."],
    "source_fingerprint": "fixture-source",
}
REPORT = {
    "observations": [{"text": "The supplied record contains batting evidence.", "fact_ids": ["F1"]}],
    "interpretations": [], "limitations": ["Coverage is incomplete."],
    "next_steps": ["Review footage before making a tactical decision."],
}


def response(content=None, finish="stop", tools=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish,
        message=SimpleNamespace(content=json.dumps(REPORT) if content is None else content, tool_calls=tools),
    )])


class ScoutAgentTests(unittest.TestCase):
    def setUp(self):
        self.secret_patch = patch.object(agents.st, "secrets", {"DEEPSEEK_API_KEY": "fixture-only"})
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.chat.completions.create.return_value = response()
        self.factory_patch = patch("openai.OpenAI", return_value=self.client)
        self.factory = self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)

    def test_valid_response_and_bounded_request(self):
        result = agents.generate_player_scout_report(copy.deepcopy(PACKET))
        self.assertEqual(result["observations"], REPORT["observations"])
        self.assertEqual(result["_provenance"]["context_fingerprint"], agents.scout_context_fingerprint(PACKET))
        options = self.factory.call_args.kwargs
        self.assertEqual(options["base_url"], "https://api.deepseek.com")
        self.assertEqual(options["max_retries"], 0)
        self.assertEqual(options["timeout"], 45.0)
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertNotIn("tools", request)
        self.assertNotIn("fixture-only", json.dumps(request))

    def test_fenced_json_is_accepted_without_rewriting_content(self):
        report = copy.deepcopy(REPORT)
        report["observations"][0]["text"] = "The literal marker ``` is retained in the evidence discussion."
        encoded = json.dumps(report)
        for text in [f"```json\n{encoded}\n```", f"```JSON\r\n{encoded}\r\n```",
                     f"```\n{encoded}\n```", "\ufeff " + encoded]:
            with self.subTest(text=text), patch.object(agents.st, "error") as debug:
                self.client.chat.completions.create.return_value = response(text)
                result = agents.generate_player_scout_report(copy.deepcopy(PACKET))
                self.assertEqual(result["observations"], report["observations"])
                debug.assert_not_called()

    def test_invalid_json_and_schema_show_raw_completion(self):
        wrong_type = copy.deepcopy(REPORT)
        wrong_type["limitations"] = "A string instead of a JSON array"
        too_many = copy.deepcopy(REPORT)
        too_many["next_steps"] = ["Review evidence."] * 7
        cases = ["```json\nnot valid json\n```", json.dumps(wrong_type), json.dumps(too_many)]
        for text in cases:
            with self.subTest(text=text), patch.object(agents.st, "error") as debug:
                self.client.chat.completions.create.return_value = response(text)
                with self.assertRaises(agents.ScoutReportError):
                    agents.generate_player_scout_report(copy.deepcopy(PACKET))
                self.assertIn(text, debug.call_args.args[0])

    def test_debug_redacts_key_and_api_failures_do_not_dump_bodies(self):
        with patch.object(agents.st, "error") as debug:
            self.client.chat.completions.create.return_value = response("invalid fixture-only output")
            with self.assertRaises(agents.ScoutReportError):
                agents.generate_player_scout_report(copy.deepcopy(PACKET))
            self.assertNotIn("fixture-only", debug.call_args.args[0])
            self.assertIn("[REDACTED API KEY]", debug.call_args.args[0])
        with patch.object(agents.st, "error") as debug:
            self.client.chat.completions.create.side_effect = RuntimeError("PRIVATE PROVIDER BODY")
            with self.assertRaises(agents.ScoutReportError):
                agents.generate_player_scout_report(copy.deepcopy(PACKET))
            debug.assert_not_called()

    def test_invalid_reports_are_rejected(self):
        bad_reference = copy.deepcopy(REPORT)
        bad_reference["observations"][0]["fact_ids"] = ["F999"]
        numerical_prose = copy.deepcopy(REPORT)
        numerical_prose["observations"][0]["text"] = "The player scored 999 runs."
        unsupported_field = dict(REPORT, prediction="Winner")
        cases = [response(" "), response("not json"), response(finish="length"),
                 response(tools=[{"name": "change_filters"}]),
                 response('{"observations":[],"observations":[]}'),
                 response(json.dumps(bad_reference)), response(json.dumps(numerical_prose)),
                 response(json.dumps(unsupported_field)), SimpleNamespace(choices=[])]
        for case in cases:
            with self.subTest(case=case):
                self.client.chat.completions.create.return_value = case
                with self.assertRaises(agents.ScoutReportError):
                    agents.generate_player_scout_report(copy.deepcopy(PACKET))

    def test_missing_key_and_invalid_evidence_make_no_request(self):
        with patch.object(agents.st, "secrets", {}):
            with self.assertRaises(agents.ScoutReportError):
                agents.generate_player_scout_report(copy.deepcopy(PACKET))
        bad = copy.deepcopy(PACKET)
        bad["facts"][0]["value"] = float("nan")
        with self.assertRaises(agents.ScoutReportError):
            agents.generate_player_scout_report(bad)
        self.factory.assert_not_called()

    def test_provider_failures_are_sanitized(self):
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        failures = [APITimeoutError(request=request),
                    AuthenticationError("DO_NOT_SHOW", response=httpx.Response(401, request=request), body={}),
                    RateLimitError("DO_NOT_SHOW", response=httpx.Response(429, request=request), body={}),
                    APIConnectionError(message="DO_NOT_SHOW", request=request),
                    APIStatusError("DO_NOT_SHOW", response=httpx.Response(503, request=request), body={}),
                    RuntimeError("DO_NOT_SHOW")]
        for failure in failures:
            self.client.chat.completions.create.side_effect = failure
            with self.assertRaises(agents.ScoutReportError) as error:
                agents.generate_player_scout_report(copy.deepcopy(PACKET))
            self.assertNotIn("DO_NOT_SHOW", str(error.exception))

    def test_fingerprint_tracks_scope_data_and_model(self):
        original = agents.scout_context_fingerprint(PACKET)
        changed = copy.deepcopy(PACKET)
        changed["scope"]["competition"] = "T20I"
        self.assertNotEqual(original, agents.scout_context_fingerprint(changed))
        changed = copy.deepcopy(PACKET)
        changed["facts"][0]["value"] = 21
        self.assertNotEqual(original, agents.scout_context_fingerprint(changed))
        with patch.object(agents.st, "secrets", {"DEEPSEEK_MODEL": "another-model"}):
            self.assertNotEqual(original, agents.scout_context_fingerprint(PACKET))

    def test_module_import_does_not_require_openai(self):
        real_import = builtins.__import__
        def blocked_import(name, *args, **kwargs):
            if name == "openai" or name.startswith("openai."):
                raise ModuleNotFoundError("Fixture: openai is unavailable")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=blocked_import):
            spec = importlib.util.spec_from_file_location("scout_without_sdk", ROOT / "agents.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with self.assertRaises(module.ScoutReportError):
                module._load_openai()

    def test_missing_sdk_preserves_all_workspaces(self):
        real_import = builtins.__import__
        def blocked_import(name, *args, **kwargs):
            if name == "openai" or name.startswith("openai."):
                raise ModuleNotFoundError("Fixture: openai is unavailable")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=blocked_import):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
            app.secrets["DEEPSEEK_API_KEY"] = "fixture-only"
            app.run()
            for route in ["Player Profile", "Team Matchups", "Auction Trends", "Home/Overview"]:
                app.sidebar.radio[0].set_value(route).run()
                self.assertFalse(app.exception, route)
            app.sidebar.radio[0].set_value("Player Profile").run()
            next(b for b in app.button if b.label == "Generate Scouting Report").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertTrue(app.metric)
            self.factory.assert_not_called()

    def test_ui_generation_cache_stale_context_and_existing_routes(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.secrets["DEEPSEEK_API_KEY"] = "fixture-only"
        app.run()
        app.sidebar.radio[0].set_value("Player Profile").run()
        app.selectbox[0].set_value("ba607b88").run()
        self.assertFalse(app.exception)
        self.client.chat.completions.create.assert_not_called()
        button = lambda: next(b for b in app.button if b.label == "Generate Scouting Report")
        button().click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(self.client.chat.completions.create.call_count, 1)
        request = self.client.chat.completions.create.call_args.kwargs
        packet = json.loads(request["messages"][1]["content"].split("\n", 1)[1])
        self.assertEqual(packet["player"]["id"], "ba607b88")
        self.assertEqual(next(f["value"] for f in packet["facts"] if f["id"] == "F1"), 9336)
        self.assertEqual(len(packet["recent_matches"]), 10)
        fact_ids = {fact["id"] for fact in packet["facts"]}
        self.assertTrue(all(row["fact_id"] in fact_ids for row in packet["recent_matches"]))
        self.assertIn("source_fingerprint", packet)
        button().click().run()
        self.assertEqual(self.client.chat.completions.create.call_count, 1)
        app.selectbox[1].set_value("All supplied competitions").run()
        self.assertTrue(any("different evidence" in info.value for info in app.info))
        self.assertFalse(any(m.value == "**Evidence-backed observations**" for m in app.markdown))
        button().click().run()
        self.assertEqual(self.client.chat.completions.create.call_count, 2)
        for route in ["Team Matchups", "Auction Trends", "Home/Overview", "Player Profile"]:
            app.sidebar.radio[0].set_value(route).run()
            self.assertFalse(app.exception, route)

    def test_ui_failure_preserves_statistics(self):
        self.client.chat.completions.create.return_value = response("bad json")
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.secrets["DEEPSEEK_API_KEY"] = "fixture-only"
        app.run()
        app.sidebar.radio[0].set_value("Player Profile").run()
        app.selectbox[0].set_value("ba607b88").run()
        next(b for b in app.button if b.label == "Generate Scouting Report").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertTrue(any("bad json" in error.value for error in app.error))
        self.assertEqual(app.metric[0].value, "9,336")


if __name__ == "__main__":
    unittest.main()
