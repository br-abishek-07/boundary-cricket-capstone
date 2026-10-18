"""Hosted startup regression: old modules, installed-name collisions and foreign cwd."""

import importlib, json, os, sys, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
GENERIC_NAMES = ("analytics", "agent", "prediction", "storage", "branding")


class Startup(unittest.TestCase):
    def run_app(self):
        a = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        self.assertFalse(a.exception, [x.message for x in a.exception])
        self.assertTrue(any("From a cricket question" in x.value for x in a.markdown))
        return a

    def test_cached_generic_modules_do_not_break_startup(self):
        stale = {name: types.ModuleType(name) for name in GENERIC_NAMES}
        for name, module in stale.items():
            module.__file__ = "/simulated/older-release/" + name + ".py"
        original = {name: sys.modules.get(name) for name in GENERIC_NAMES}
        try:
            for name, module in stale.items():
                sys.modules[name] = module
            with tempfile.TemporaryDirectory() as d, patch.dict(
                os.environ, {"BOUNDARY_RUNTIME_DIR": d}
            ):
                a = self.run_app()
                for name, module in stale.items():
                    self.assertIs(sys.modules[name], module)
                # A rerun must use the packaged functions while the old modules remain cached.
                a.sidebar.radio[0].set_value("Decision desk").run()
                next(x for x in a.button if x.label == "Prepare brief").click().run()
                self.assertFalse(a.exception, [x.message for x in a.exception])
                self.assertEqual(a.session_state["brief"]["status"], "evidence_checked")
        finally:
            for name, module in original.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def test_startup_from_another_working_directory(self):
        before = os.getcwd()
        old_path = sys.path[:]
        with tempfile.TemporaryDirectory() as d, patch.dict(
            os.environ, {"BOUNDARY_RUNTIME_DIR": d}
        ):
            try:
                os.chdir(d)
                sys.path[:] = [x for x in sys.path if x != str(ROOT)]
                self.run_app()
            finally:
                os.chdir(before)
                sys.path[:] = old_path

    def test_packaged_resources_resolve_to_repository(self):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        for name in GENERIC_NAMES:
            with self.subTest(module=name):
                module = importlib.import_module("boundary_core." + name)
                self.assertEqual(module.ROOT, ROOT)
                self.assertEqual(
                    Path(module.__file__).resolve().parent, ROOT / "boundary_core"
                )
        from boundary_core import branding

        for team in (*branding.TEAMS, "IPL"):
            self.assertTrue(
                branding.logo(team).startswith("data:image/svg+xml;base64,")
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
