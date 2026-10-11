"""Transform agency GTFS snapshots into a geographic reference layer, not simulation demand."""
import argparse,csv,io,json,hashlib
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from zipfile import ZipFile

def simplify(points,tolerance=.000035):
    if len(points)<3:return points
    a,b=points[0],points[-1];dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
    distances=[]
    for p in points[1:-1]:
        t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
        distances.append((p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2)
    maximum=max(distances,default=0)
    if maximum<=tolerance*tolerance:return [a,b]
    index=distances.index(maximum)+1
    return simplify(points[:index+1],tolerance)[:-1]+simplify(points[index:],tolerance)

def parse(path,operator,url):
    with ZipFile(path) as z:
        def rows(name):
            if name not in z.namelist():return iter(())
            return csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig'))
        routes={r['route_id']:r for r in rows('routes.txt')}
        trips={t['trip_id']:t for t in rows('trips.txt')}
        shape_routes=defaultdict(set);stop_routes=defaultdict(set)
        for t in trips.values():shape_routes[t.get('shape_id','')].add(t['route_id'])
        for t in rows('stop_times.txt'):
            trip=trips.get(t['trip_id']);
            if trip:stop_routes[t['stop_id']].add(trip['route_id'])
        rawstops={s['stop_id']:s for s in rows('stops.txt')}
        merged=defaultdict(set)
        for sid,rs in stop_routes.items():
            s=rawstops.get(sid,{})
            parent=s.get('parent_station','') if operator=='BART' else ''
            merged[parent or sid].update(rs)
        stops=[]
        for sid,rs in merged.items():
            s=rawstops.get(sid)
            if not s or not s.get('stop_lat') or not s.get('stop_lon'):continue
            stops.append(dict(id=f'{operator}:{sid}',name=s['stop_name'],lat=float(s['stop_lat']),lon=float(s['stop_lon']),operator=operator,routes=sorted(rs),rail=any(routes[r]['route_type']!='3' for r in rs)))
        shapes=defaultdict(list)
        for s in rows('shapes.txt'):
            if s['shape_id'] in shape_routes:shapes[s['shape_id']].append((int(s['shape_pt_sequence']),float(s['shape_pt_lat']),float(s['shape_pt_lon'])))
        outputroutes=[]
        for rid,r in routes.items():
            geometries=[];seen=set()
            for sid in sorted(s for s,rs in shape_routes.items() if rid in rs):
                pts=simplify([[round(lat,6),round(lon,6)] for _,lat,lon in sorted(shapes[sid])])
                key=json.dumps(pts)
                if len(pts)>1 and key not in seen:geometries.append(pts);seen.add(key)
            outputroutes.append(dict(id=f'{operator}:{rid}',feed_route_id=rid,operator=operator,short_name=r['route_short_name'],name=r['route_long_name'],route_type=int(r['route_type']),color='#'+r.get('route_color','75c7f2').strip(),paths=geometries))
        calendar=list(rows('calendar.txt'));feed=list(rows('feed_info.txt'))
        end=max((r.get('end_date','') for r in calendar),default='')
        if feed:end=feed[0].get('feed_end_date') or end
        provenance=dict(operator=operator,url=url,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),retrieved_at=datetime.now(timezone.utc).isoformat(),feed_end_date=end,feed_info=feed,transformation='GTFS route/trip/stop-time joins; BART platforms grouped by parent station; all referenced shape variants simplified ~4m, rounded to 6 decimals; no passenger demand inferred',license_url='https://www.bart.gov/schedules/developers/developer-license-agreement' if operator=='BART' else 'https://www.sfmta.com/reports/gtfs-transit-data')
        return dict(stops=stops,routes=outputroutes,provenance=provenance)

def main():
    p=argparse.ArgumentParser();p.add_argument('--muni',required=True);p.add_argument('--bart',required=True);p.add_argument('--output',default='frontend/public/data/transit-reference.json');a=p.parse_args()
    datasets=[parse(a.muni,'Muni','https://muni-gtfs.apps.sfmta.com/data/muni_gtfs-current.zip'),parse(a.bart,'BART','https://www.bart.gov/dev/schedules/google_transit.zip')]
    result=dict(kind='observed_agency_GTFS_reference_not_live_service',stops=sum((d['stops'] for d in datasets),[]),routes=sum((d['routes'] for d in datasets),[]),sources=[d['provenance'] for d in datasets])
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(json.dumps({'stops':len(result['stops']),'routes':len(result['routes']),'bytes':out.stat().st_size,'sources':[(d['provenance']['operator'],d['provenance']['feed_end_date']) for d in datasets]}))
if __name__=='__main__':main()
