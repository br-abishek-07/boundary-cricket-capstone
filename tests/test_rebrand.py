"""Product rename preserves scoped records, quota usage and branded exports."""

from pathlib import Path
import json, os, sqlite3, sys, tempfile, unittest, zipfile, io
from unittest.mock import patch

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from creaseiq_core import storage, downloads
from creaseiq_core.evidence import manifest


class Rebrand(unittest.TestCase):
    def previous(self, root, name, owner):
        c = sqlite3.connect(Path(root) / name)
        c.executescript(
            "CREATE TABLE usage(day TEXT,owner TEXT,n INTEGER NOT NULL,PRIMARY KEY(day,owner)); CREATE TABLE items(id INTEGER PRIMARY KEY,owner TEXT,kind TEXT,created TEXT,title TEXT,payload TEXT); CREATE TABLE cache(owner TEXT,k TEXT,payload TEXT,PRIMARY KEY(owner,k));"
        )
        c.execute(
            "INSERT INTO items VALUES(1,?,'brief','2026-10-18','Saved research',?)",
            (owner, json.dumps({"value": 17})),
        )
        c.execute("INSERT INTO usage VALUES('2026-10-18',?,5)", (owner,))
        c.execute("INSERT INTO cache VALUES(?,'old-fingerprint','{}')", (owner,))
        c.commit()
        c.close()

    def test_one_compatible_store_preserves_scopes_and_usage_once(self):
        owner = storage.scope("synthetic-session", "RCB")
        other = storage.scope("other-session", "RCB")
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, {"CREASEIQ_RUNTIME_DIR": root}
        ):
            self.previous(root, "previous-journal.sqlite3", owner)
            with storage.db() as c:
                self.assertEqual(
                    c.execute("SELECT n FROM usage WHERE owner=?", (owner,)).fetchone()[
                        0
                    ],
                    5,
                )
                self.assertEqual(
                    c.execute("SELECT owner FROM items").fetchone()[0], owner
                )
                self.assertEqual(
                    c.execute("SELECT k FROM cache").fetchone()[0], "old-fingerprint"
                )
            self.assertEqual(len(storage.records(owner, "brief")), 1)
            self.assertEqual(storage.records(other, "brief"), [])
            with storage.db() as c:
                self.assertEqual(
                    c.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1
                )
            self.assertTrue((Path(root) / "previous-journal.sqlite3").exists())

    def test_multiple_previous_stores_are_not_implicitly_merged(self):
        owner = storage.scope("synthetic-session", "MI")
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ, {"CREASEIQ_RUNTIME_DIR": root}
        ):
            self.previous(root, "first.sqlite3", owner)
            self.previous(root, "second.sqlite3", owner)
            self.assertEqual(storage.records(owner, "brief"), [])
            self.assertTrue((Path(root) / "first.sqlite3").exists())
            self.assertTrue((Path(root) / "second.sqlite3").exists())

    def test_export_identity_and_runnable_source_names(self):
        m = manifest("RCB", "2026-10-18", {}, "test")
        self.assertEqual(m["application"], "CreaseIQ")
        self.assertEqual(m["version"], "3.1.0")
        with zipfile.ZipFile(io.BytesIO(downloads.source_zip())) as z:
            self.assertIn("creaseiq/creaseiq_runtime.py", z.namelist())
            self.assertIn("creaseiq/creaseiq_core/agent.py", z.namelist())
            self.assertIn("creaseiq/app.py", z.namelist())
            self.assertTrue(all(n.startswith("creaseiq/") for n in z.namelist()))


if __name__ == "__main__":
    unittest.main()
