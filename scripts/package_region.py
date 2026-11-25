#!/usr/bin/env python3
"""Create a regional offline walking pack, preserving source and ODbL metadata."""
import sys, pathlib, sqlite3, hashlib, json, zipfile
REGIONS=('seoul','incheon','gyeonggi','gangwon','chungcheong','jeolla','gyeongsang','jeju')
def package(region,source,out):
    assert region in REGIONS
    source=pathlib.Path(source); out=pathlib.Path(out)
    with sqlite3.connect(source) as db:
        db.execute('CREATE INDEX IF NOT EXISTS node_lat_lon ON nodes(lat,lon)')
        db.execute('CREATE INDEX IF NOT EXISTS place_lat_lon ON places(lat,lon)')
        meta={k:json.loads(v) for k,v in db.execute('SELECT k,v FROM meta')}
        assert meta['license']=='ODbL 1.0' and meta['schema']==1
        assert meta['source']=='https://tiles.osm.kr/download/'+region+'-non-military.osm.pbf'
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        counts={x:db.execute('SELECT count(*) FROM '+x).fetchone()[0] for x in ('nodes','edges','places')}
        assert counts['nodes']>1000 and counts['edges']>1000 and counts['places']>10
    size=source.stat().st_size
    assert 0<size<=1_500_000_000
    with source.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    info={'schema':1,'region':region,'size':size,'sha256':digest,'counts':counts,'license':'ODbL 1.0','source':meta['source'],'source_sha256':meta['sha256'],'attribution':'© OpenStreetMap contributors','field_verified':False}
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        z.writestr('manifest.json',json.dumps(info,ensure_ascii=False))
        z.write(source,'walk.sqlite')
        z.writestr('LICENSE-NOTICE.txt','© OpenStreetMap contributors. Open Database License 1.0. https://www.openstreetmap.org/copyright\nRegional conservative walking graph, not field verified. Source: '+meta['source']+'\n')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        with z.open('walk.sqlite') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest
    print(json.dumps(info,ensure_ascii=False))
if __name__=='__main__':package(*sys.argv[1:])
