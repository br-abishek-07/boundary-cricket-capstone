"""Release snapshots, warm updates, bytecode and concurrent startup."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os, py_compile, shutil, sys, tempfile, types, unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from creaseiq_runtime import load_release
from creaseiq_core.downloads import source_files


class ReleaseRuntime(unittest.TestCase):
    def copy_core(self, root):
        shutil.copytree(
            ROOT / "creaseiq_core",
            root / "creaseiq_core",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    def test_01_previous_package_cannot_break_home_or_brief(self):
        names = ["creaseiq_core"] + [
            "creaseiq_core." + n
            for n in [
                "analytics",
                "prediction",
                "agent",
                "storage",
                "branding",
                "evidence",
                "downloads",
            ]
        ]
        original = {name: sys.modules.get(name) for name in names}
        stale = {name: types.ModuleType(name) for name in names}
        stale["creaseiq_core"].__path__ = [str(ROOT / "creaseiq_core")]
        for name, module in stale.items():
            module.__file__ = str(
                ROOT / "creaseiq_core" / (name.split(".")[-1] + ".py")
            )
        try:
            sys.modules.update(stale)
            self.assertFalse(hasattr(stale["creaseiq_core.agent"], "prepare"))
            with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {"CREASEIQ_RUNTIME_DIR": directory}
            ):
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
                app.session_state["brief"] = {
                    "team": "RCB",
                    "until": "2026-10-18",
                    "text": "Earlier saved answer",
                    "status": "grounded",
                }
                app.run()
                self.assertFalse(app.exception, [e.message for e in app.exception])
                app.sidebar.radio[0].set_value("Decision desk").run()
                self.assertFalse(app.exception, [e.message for e in app.exception])
                self.assertTrue(
                    any("Context changed" in warning.value for warning in app.warning)
                )
                next(b for b in app.button if b.label == "Prepare brief").click().run()
                self.assertFalse(app.exception, [e.message for e in app.exception])
                self.assertEqual(
                    app.session_state["brief"]["status"], "evidence_checked"
                )
                for name, module in stale.items():
                    self.assertIs(sys.modules[name], module)
        finally:
            for name, module in original.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def test_02_identical_code_reuses_a_coherent_graph(self):
        first = load_release(ROOT)
        second = load_release(ROOT)
        self.assertIs(first, second)
        self.assertTrue(first.release_ready)
        self.assertIs(first.agent.storage, first.storage)
        self.assertIs(first.agent.scout, first.analytics.scout)
        self.assertIs(first.agent.manifest, first.evidence.manifest)
        self.assertIs(first.agent.predict, first.prediction.predict)
        for name in [
            "storage",
            "evidence",
            "analytics",
            "prediction",
            "branding",
            "downloads",
            "agent",
        ]:
            module = getattr(first, name)
            self.assertEqual(module.ROOT, ROOT)
            self.assertTrue(module.__name__.startswith(first.__name__ + "."))

    def test_03_same_path_size_and_timestamp_still_load_changed_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_core(root)
            path = root / "creaseiq_core/evidence.py"
            source = path.read_bytes()
            stamp = path.stat()
            py_compile.compile(str(path), doraise=True)
            first = load_release(root)
            version = first.evidence.VERSION
            changed = source.replace(
                ('VERSION = "' + version + '"').encode(), b'VERSION = "9.9.9"'
            )
            self.assertEqual(len(changed), len(source))
            path.write_bytes(changed)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            second = load_release(root)
            self.assertIsNot(first, second)
            self.assertEqual(second.evidence.VERSION, "9.9.9")
            self.assertEqual(first.evidence.VERSION, version)
            self.assertEqual(second.agent.manifest.__globals__["VERSION"], "9.9.9")
            self.assertIs(second.agent.scout, second.analytics.scout)

    def test_04_failed_snapshot_leaves_no_partial_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_core(root)
            path = root / "creaseiq_core/agent.py"
            source = path.read_bytes()
            before = set(sys.modules)
            path.write_bytes(source + b"\ndef incomplete(\n")
            with self.assertRaises(SyntaxError):
                load_release(root)
            leaked = {
                n
                for n in set(sys.modules) - before
                if n.startswith("_creaseiq_release_")
            }
            self.assertEqual(leaked, set())
            path.write_bytes(source)
            self.assertTrue(load_release(root).release_ready)

    def test_05_concurrent_startup_shares_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_core(root)
            with ThreadPoolExecutor(max_workers=8) as executor:
                releases = list(executor.map(load_release, [root] * 16))
            self.assertTrue(all(r is releases[0] and r.release_ready for r in releases))
            self.assertIs(releases[0].agent.storage, releases[0].storage)

    def test_06_code_update_invalidates_data_cache_in_same_session(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CREASEIQ_RUNTIME_DIR": str(Path(directory) / "runtime")}
        ):
            root = Path(directory) / "project"
            for path in source_files():
                target = root / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            path = root / "creaseiq_core/analytics.py"
            original = path.read_text()
            marked = original.replace(
                "    return p, s, a",
                '    s.attrs["cache_marker"] = "before"\n    return p, s, a',
                1,
            )
            path.write_text(marked)
            entry = root / "app.py"
            entry.write_text(
                entry.read_text()
                + '\nst.caption("CACHE MARKER " + s.attrs.get("cache_marker", "missing"))\n'
            )
            app = AppTest.from_file(str(entry), default_timeout=60).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("CACHE MARKER before" in x.value for x in app.caption))
            data_mtimes = {
                p: p.stat().st_mtime_ns
                for p in (root / "data").iterdir()
                if p.is_file()
            }
            stamp = path.stat()
            path.write_text(marked.replace('"before"', '"after!"'))
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            app.run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertTrue(any("CACHE MARKER after!" in x.value for x in app.caption))
            self.assertTrue(
                all(p.stat().st_mtime_ns == stamp for p, stamp in data_mtimes.items())
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
