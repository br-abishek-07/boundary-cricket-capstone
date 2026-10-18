"""Local decision journal and persistent provider-call allowance; never stores API keys."""
from pathlib import Path
from contextlib import contextmanager
import datetime,json,os,sqlite3
ROOT=Path(__file__).parent
@contextmanager
def db():
 path=Path(os.getenv('BOUNDARY_RUNTIME_DIR',str(ROOT/'.runtime')));path.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(path/'boundary.sqlite3',timeout=10)
 c.execute('CREATE TABLE IF NOT EXISTS calls(day TEXT PRIMARY KEY,n INTEGER NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS briefs(id INTEGER PRIMARY KEY,created TEXT,title TEXT,payload TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,created TEXT,reviewer TEXT,payload TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY,payload TEXT)');c.commit()
 try:yield c
 finally:c.close()
def reserve_call(limit=30):
 day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 with db() as c:
  c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT n FROM calls WHERE day=?',(day,)).fetchone();n=row[0] if row else 0
  if n>=limit:c.rollback();raise RuntimeError('Daily allowance reached (30 provider requests). Local tools remain available.')
  c.execute('INSERT INTO calls VALUES (?,1) ON CONFLICT(day) DO UPDATE SET n=n+1',(day,));c.commit()
def cached(k):
 with db() as c:r=c.execute('SELECT payload FROM cache WHERE k=?',(k,)).fetchone()
 return json.loads(r[0]) if r else None
def cache(k,payload):
 with db() as c:c.execute('INSERT OR REPLACE INTO cache VALUES (?,?)',(k,json.dumps(payload,allow_nan=False)));c.commit()
def save(kind,title,payload):
 with db() as c:
  col='title' if kind=='briefs' else 'reviewer';table='briefs' if kind=='briefs' else 'reviews'
  c.execute(f'INSERT INTO {table}(created,{col},payload) VALUES (?,?,?)',(datetime.datetime.now(datetime.timezone.utc).isoformat(),title,json.dumps(payload,allow_nan=False)));c.commit()
def records(kind='briefs'):
 table='briefs' if kind=='briefs' else 'reviews'
 with db() as c:
  rows=c.execute(f'SELECT * FROM {table} ORDER BY id DESC').fetchall()
 return [{'id':r[0],'created':r[1],'title':r[2],'payload':json.loads(r[3])} for r in rows]
