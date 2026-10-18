"""Session-and-franchise-scoped storage; legacy unscoped records are never returned."""
from pathlib import Path
from contextlib import contextmanager
import datetime,hashlib,json,os,sqlite3
ROOT=Path(__file__).parent
@contextmanager
def db():
 root=Path(os.getenv('BOUNDARY_RUNTIME_DIR',str(ROOT/'.runtime')));root.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(root/'boundary-v2.sqlite3',timeout=10);c.execute('PRAGMA journal_mode=WAL')
 c.execute('CREATE TABLE IF NOT EXISTS usage(day TEXT, owner TEXT,n INTEGER NOT NULL,PRIMARY KEY(day,owner))')
 c.execute('CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,owner TEXT,kind TEXT,created TEXT,title TEXT,payload TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS cache(owner TEXT,k TEXT,payload TEXT,PRIMARY KEY(owner,k))');c.commit()
 try:yield c
 finally:c.close()
def scope(session,team):
 if not session or not team:raise ValueError('A private session and franchise scope are required.')
 return hashlib.sha256((session+'|'+team).encode()).hexdigest()
def require(owner):
 if not isinstance(owner,str) or len(owner)!=64:raise ValueError('Private scope is required.')
def reserve_call(owner,global_limit=30,session_limit=6):
 require(owner);day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 with db() as c:
  c.execute('BEGIN IMMEDIATE');rows=dict(c.execute('SELECT owner,n FROM usage WHERE day=?',(day,)));total=sum(rows.values())
  if total>=global_limit or rows.get(owner,0)>=session_limit:c.rollback();raise RuntimeError('AI request allowance reached. Local evidence tools and saved work remain available.')
  c.execute('INSERT INTO usage VALUES (?,?,1) ON CONFLICT(day,owner) DO UPDATE SET n=n+1',(day,owner));c.commit()
def usage(owner):
 require(owner);day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 with db() as c:rows=dict(c.execute('SELECT owner,n FROM usage WHERE day=?',(day,)))
 return {'session_requests':rows.get(owner,0),'installation_requests':sum(rows.values()),'session_limit':6,'installation_limit':30}
def cached(owner,k):
 require(owner)
 with db() as c:r=c.execute('SELECT payload FROM cache WHERE owner=? AND k=?',(owner,k)).fetchone()
 return json.loads(r[0]) if r else None
def cache(owner,k,payload):
 require(owner)
 with db() as c:c.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',(owner,k,json.dumps(payload,allow_nan=False)));c.commit()
def save(owner,kind,title,payload):
 require(owner)
 if kind not in ['briefs','reviews']:raise ValueError('Unknown journal type.')
 with db() as c:c.execute('INSERT INTO items(owner,kind,created,title,payload) VALUES (?,?,?,?,?)',(owner,kind,datetime.datetime.now(datetime.timezone.utc).isoformat(),title,json.dumps(payload,allow_nan=False)));c.commit()
def records(owner,kind='briefs'):
 require(owner)
 with db() as c:r=c.execute('SELECT id,created,title,payload FROM items WHERE owner=? AND kind=? ORDER BY id DESC',(owner,kind)).fetchall()
 return [{'id':x[0],'created':x[1],'title':x[2],'payload':json.loads(x[3])} for x in r]
