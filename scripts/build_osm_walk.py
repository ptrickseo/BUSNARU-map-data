#!/usr/bin/env python3
"""Build conservative pedestrian graph + local place index from licensed regional OSM.
PBF needs pyosmium; XML fixtures use standard library. No external routing API.
"""
import argparse,collections,functools,hashlib,heapq,json,math,pathlib,sqlite3,unicodedata,xml.etree.ElementTree as ET
ALLOWED={'footway','pedestrian','path','steps','living_street','residential','unclassified','service','tertiary','tertiary_link','track'}
ARTERIAL={'primary','primary_link','secondary','secondary_link','trunk','trunk_link'}
DENIED={'no','private','destination','customers','delivery','agricultural','forestry','permit','military','restricted'}
BARRIERS={'fence','wall','gate','lift_gate','swing_gate','chain','block','turnstile','stile','hedge','ditch','bollard','jersey_barrier','kissing_gate','cycle_barrier','sally_port','hampshire_gate'}
PERMITTED={'yes','designated','permissive'}
def norm(s):return ' '.join(unicodedata.normalize('NFKC',s).casefold().split())
def valid(lat,lon):return math.isfinite(lat) and math.isfinite(lon) and 30<=lat<=40 and 120<=lon<=135
def distance(a,b):
    r=math.pi/180;x=(b[0]-a[0])*r;y=(b[1]-a[1])*r
    q=math.sin(x/2)**2+math.cos(a[0]*r)*math.cos(b[0]*r)*math.sin(y/2)**2
    return 6371000*2*math.asin(math.sqrt(max(0,min(1,q))))
def policy(t):
    h=t.get('highway','')
    if t.get('access') in DENIED or t.get('foot') in DENIED or t.get('area')=='yes' or t.get('motorroad')=='yes':return None
    if any(k in t for k in ('access:conditional','foot:conditional','opening_hours','construction','proposed')):return None
    if h not in ALLOWED:
        if h not in ARTERIAL or t.get('foot') not in PERMITTED or t.get('sidewalk') not in ('both','left','right','yes'):return None
    if t.get('sidewalk')=='separate' and h not in ('footway','pedestrian','path','steps'):return None
    if h=='service' and t.get('service') in ('driveway','parking_aisle','emergency_access') and t.get('foot') not in PERMITTED:return None
    if h in ('path','track') and t.get('foot') not in PERMITTED:return None
    if t.get('ford') not in (None,'no'):return None
    f=t.get('oneway:foot','no');forward=f!='-1';backward=f not in ('yes','1','true')
    if f not in ('no','0','false','yes','1','true','-1'):return None
    if t.get('foot:forward') in DENIED:forward=False
    if t.get('foot:backward') in DENIED:backward=False
    # Wheelchair support unknown unless explicitly indicated; never infer from geometry.
    accessible=t.get('wheelchair')=='yes' and h!='steps' and t.get('incline') in (None,'0','0%') and t.get('surface') in ('paved','asphalt','concrete','paving_stones')
    return forward,backward,int(accessible)
def node_blocked(t):
    return t.get('foot') in DENIED or t.get('access') in DENIED or 'access:conditional' in t or 'foot:conditional' in t or (t.get('barrier') in BARRIERS and t.get('foot') not in PERMITTED)
class Builder:
    def __init__(self,db):
        self.db=db;self.block=set();self.n=collections.Counter()
        db.executescript("""PRAGMA journal_mode=OFF;PRAGMA synchronous=OFF;
        CREATE TABLE nodes(id INTEGER PRIMARY KEY,lat REAL NOT NULL,lon REAL NOT NULL);
        CREATE TABLE edges(src INTEGER,dst INTEGER,meters REAL NOT NULL,way INTEGER NOT NULL,accessible INTEGER NOT NULL,PRIMARY KEY(src,dst,way)) WITHOUT ROWID;
        CREATE TABLE places(id INTEGER PRIMARY KEY,osm_type TEXT,osm_id INTEGER,name TEXT,norm TEXT,kind TEXT,lat REAL,lon REAL,UNIQUE(osm_type,osm_id));
        CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT);""")
    def place(self,typ,i,t,lat,lon):
        name=t.get('name','').strip()
        kind=next((t[k] for k in ('amenity','shop','tourism','leisure','public_transport','railway','place') if t.get(k)),None)
        if not name or not kind or len(name)>300 or not valid(lat,lon):return
        if t.get('access') in DENIED or t.get('military') or t.get('landuse')=='military':return
        self.db.execute('INSERT OR IGNORE INTO places(osm_type,osm_id,name,norm,kind,lat,lon) VALUES(?,?,?,?,?,?,?)',(typ,i,name,norm(name),kind,lat,lon))
    def node(self,i,t,lat,lon):
        if node_blocked(t):self.block.add(i)
        self.place('node',i,t,lat,lon)
    def way(self,i,t,refs):
        p=policy(t)
        if not p:return
        f,b,a=p;self.n['walkable_ways']+=1
        for (u,x),(v,y) in zip(refs,refs[1:]):
            if x is None or y is None or u==v or u in self.block or v in self.block or not valid(*x) or not valid(*y):continue
            d=distance(x,y)
            if not 0<d<=20000:continue
            self.db.executemany('INSERT OR IGNORE INTO nodes VALUES(?,?,?)',((u,*x),(v,*y)))
            if f:self.db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?,?,?)',(u,v,d,i,a))
            if b:self.db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?,?,?)',(v,u,d,i,a))
def from_xml(src,b):
    coords={}
    # Standard sorted OSM XML (nodes before ways), explicit references only.
    for _,el in ET.iterparse(src,events=('end',)):
        if el.tag=='node':
            i=int(el.attrib['id']);lat=float(el.attrib['lat']);lon=float(el.attrib['lon']);t={x.attrib['k']:x.attrib['v'] for x in el if x.tag=='tag'}
            coords[i]=(lat,lon);b.node(i,t,lat,lon);el.clear()
        elif el.tag=='way':
            t={x.attrib['k']:x.attrib['v'] for x in el if x.tag=='tag'}
            refs=[int(x.attrib['ref']) for x in el if x.tag=='nd']
            b.way(int(el.attrib['id']),t,[(i,coords.get(i)) for i in refs]);el.clear()
def from_pbf(src,b):
    import osmium
    class Handler(osmium.SimpleHandler):
        def node(self,n):
            if n.location.valid():b.node(n.id,dict(n.tags),n.location.lat,n.location.lon)
        def way(self,w):
            t=dict(w.tags)
            if not policy(t):return
            b.way(w.id,t,[(n.ref,(n.location.lat,n.location.lon) if n.location.valid() else None) for n in w.nodes])
    Handler().apply_file(str(src),locations=True,idx='flex_mem')
def build(src,out,source):
    src=pathlib.Path(src);out=pathlib.Path(out);tmp=out.with_suffix('.partial')
    if out.exists() or tmp.exists():raise FileExistsError(out)
    db=sqlite3.connect(tmp)
    try:
        b=Builder(db)
        if src.name.endswith('.pbf'):from_pbf(src,b)
        elif src.name.endswith('.osm'):from_xml(src,b)
        else:raise ValueError('requires .osm or .osm.pbf')
        # Remove all edges touching a blocked node even if input ordering was unusual.
        db.executemany('DELETE FROM edges WHERE src=?',((x,) for x in b.block))
        db.execute('CREATE INDEX edge_dst ON edges(dst)')
        db.executemany('DELETE FROM edges WHERE dst=?',((x,) for x in b.block))
        db.execute('CREATE INDEX places_norm ON places(norm)')
        counts={k:db.execute('SELECT COUNT(*) FROM '+k).fetchone()[0] for k in ('nodes','edges','places')}
        if not counts['edges']:raise ValueError('empty pedestrian graph')
        with src.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
        meta={'schema':1,'source':source,'sha256':sha,'attribution':'© OpenStreetMap contributors','license':'ODbL 1.0','license_url':'https://www.openstreetmap.org/copyright','counts':counts,'field_verified':False,'policy':'conservative mapped connectivity; incomplete, no coordinate snapping or unverified crossing'}
        db.executemany('INSERT INTO meta VALUES(?,?)',((k,json.dumps(v,ensure_ascii=False)) for k,v in meta.items()))
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('integrity')
        db.close();tmp.replace(out);print(json.dumps(meta,ensure_ascii=False))
    except BaseException:
        db.close();tmp.unlink(missing_ok=True);raise
def connect(path):
    db=sqlite3.connect(pathlib.Path(path).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
def search(path,q,limit=20):
    q=norm(q)
    if not q or len(q)>100:return []
    db=connect(path)
    try:return [dict(x) for x in db.execute('SELECT name,kind,lat,lon,osm_id,osm_type FROM places WHERE norm>=? AND norm<? ORDER BY norm LIMIT ?',(q,q+chr(0x10ffff),max(1,min(50,int(limit)))))]
    finally:db.close()
def route(path,src,dst,max_meters=10000,accessible=False,max_work=150000):
    if not math.isfinite(max_meters) or not 0<=max_meters<=50000:raise ValueError('distance limit')
    db=connect(path)
    try:
        if not all(db.execute('SELECT 1 FROM nodes WHERE id=?',(i,)).fetchone() for i in (src,dst)):return {'status':'UNKNOWN_NODE'}
        dist={src:0};prev={};h=[(0,src)];work=0
        while h:
            d,u=heapq.heappop(h)
            if d!=dist.get(u):continue
            if u==dst:
                ids=[u]
                while ids[-1]!=src:ids.append(prev[ids[-1]])
                ids.reverse()
                geo=[list(db.execute('SELECT lon,lat FROM nodes WHERE id=?',(x,)).fetchone()) for x in ids]
                return {'status':'OK','meters':round(d,1),'nodes':ids,'geometry':geo,'source':'OSM mapped pedestrian edges','field_verified':False}
            for x in db.execute('SELECT dst,meters,accessible FROM edges WHERE src=?',(u,)):
                work+=1
                if work>max_work:return {'status':'SEARCH_LIMIT'}
                v=x['dst'];n=d+x['meters']
                if (accessible and x['accessible']!=1) or n>max_meters or n>=dist.get(v,math.inf):continue
                dist[v]=n;prev[v]=u;heapq.heappush(h,(n,v))
        return {'status':'NO_PATH_IN_LOADED_GRAPH'}
    finally:db.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--source-url',required=True);a=p.parse_args();build(a.source,a.output,a.source_url)
