"""Session-and-franchise-scoped storage; legacy unscoped records are never returned."""

from pathlib import Path
from contextlib import contextmanager
import datetime, hashlib, json, os, sqlite3

ROOT = Path(__file__).resolve().parents[1]


def _adopt_previous_store(c, root, destination):
    """Copy one compatible prior store without deleting it or changing scopes.

    The one-time transaction also preserves usage limits across a product rename.
    Multiple compatible stores are left untouched rather than merged implicitly.
    """
    expected = {
        "usage": ["day", "owner", "n"],
        "items": ["id", "owner", "kind", "created", "title", "payload"],
        "cache": ["owner", "k", "payload"],
    }
    c.execute("CREATE TABLE IF NOT EXISTS metadata(k TEXT PRIMARY KEY,v TEXT)")
    c.execute("BEGIN IMMEDIATE")
    attached = False
    try:
        done = c.execute(
            "SELECT v FROM metadata WHERE k='previous_store_reviewed'"
        ).fetchone()
        if done:
            c.commit()
            return
        occupied = any(
            c.execute("SELECT 1 FROM " + table + " LIMIT 1").fetchone()
            for table in expected
        )
        candidates = []
        if not occupied:
            for path in root.glob("*.sqlite3"):
                if path == destination or path.is_symlink():
                    continue
                old = None
                try:
                    old = sqlite3.connect(
                        path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
                    )
                    if all(
                        [
                            row[1]
                            for row in old.execute("PRAGMA table_info(" + name + ")")
                        ]
                        == columns
                        for name, columns in expected.items()
                    ):
                        candidates.append(path)
                except sqlite3.Error:
                    pass
                finally:
                    if old is not None:
                        old.close()
        status = "existing_store" if occupied else "no_single_compatible_store"
        if len(candidates) == 1:
            c.execute("ATTACH DATABASE ? AS previous_store", (str(candidates[0]),))
            attached = True
            for name, columns in expected.items():
                cols = ",".join(columns)
                c.execute(
                    "INSERT OR IGNORE INTO "
                    + name
                    + "("
                    + cols
                    + ") SELECT "
                    + cols
                    + " FROM previous_store."
                    + name
                )
            status = "copied_compatible_store"
        c.execute(
            "INSERT INTO metadata(k,v) VALUES('previous_store_reviewed',?)", (status,)
        )
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        if attached:
            c.execute("DETACH DATABASE previous_store")


@contextmanager
def db():
    root = Path(os.getenv("CREASEIQ_RUNTIME_DIR", str(ROOT / ".runtime")))
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "creaseiq.sqlite3"
    c = sqlite3.connect(destination, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(
        "CREATE TABLE IF NOT EXISTS usage(day TEXT, owner TEXT,n INTEGER NOT NULL,PRIMARY KEY(day,owner))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,owner TEXT,kind TEXT,created TEXT,title TEXT,payload TEXT)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS cache(owner TEXT,k TEXT,payload TEXT,PRIMARY KEY(owner,k))"
    )
    c.commit()
    _adopt_previous_store(c, root, destination)
    try:
        yield c
    finally:
        c.close()


def scope(session, team):
    if not session or not team:
        raise ValueError("A private session and franchise scope are required.")
    return hashlib.sha256((session + "|" + team).encode()).hexdigest()


def require(owner):
    if not isinstance(owner, str) or len(owner) != 64:
        raise ValueError("Private scope is required.")


def reserve_call(owner, global_limit=30, session_limit=6):
    require(owner)
    day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        rows = dict(c.execute("SELECT owner,n FROM usage WHERE day=?", (day,)))
        total = sum(rows.values())
        if total >= global_limit or rows.get(owner, 0) >= session_limit:
            c.rollback()
            raise RuntimeError(
                "AI request allowance reached. Local evidence tools and saved work remain available."
            )
        c.execute(
            "INSERT INTO usage VALUES (?,?,1) ON CONFLICT(day,owner) DO UPDATE SET n=n+1",
            (day, owner),
        )
        c.commit()


def usage(owner):
    require(owner)
    day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    with db() as c:
        rows = dict(c.execute("SELECT owner,n FROM usage WHERE day=?", (day,)))
    return {
        "session_requests": rows.get(owner, 0),
        "installation_requests": sum(rows.values()),
        "session_limit": 6,
        "installation_limit": 30,
    }


def cached(owner, k):
    require(owner)
    with db() as c:
        r = c.execute(
            "SELECT payload FROM cache WHERE owner=? AND k=?", (owner, k)
        ).fetchone()
    return json.loads(r[0]) if r else None


def cache(owner, k, payload):
    require(owner)
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
            (owner, k, json.dumps(payload, allow_nan=False)),
        )
        c.commit()


def save(owner, kind, title, payload):
    require(owner)
    if kind not in ["briefs", "reviews"]:
        raise ValueError("Unknown journal type.")
    with db() as c:
        c.execute(
            "INSERT INTO items(owner,kind,created,title,payload) VALUES (?,?,?,?,?)",
            (
                owner,
                kind,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                title,
                json.dumps(payload, allow_nan=False),
            ),
        )
        c.commit()


def records(owner, kind="briefs"):
    require(owner)
    with db() as c:
        r = c.execute(
            "SELECT id,created,title,payload FROM items WHERE owner=? AND kind=? ORDER BY id DESC",
            (owner, kind),
        ).fetchall()
    return [
        {"id": x[0], "created": x[1], "title": x[2], "payload": json.loads(x[3])}
        for x in r
    ]
