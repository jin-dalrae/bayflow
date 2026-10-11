import json
from pathlib import Path
from scripts.build_map_reference import simplify


def test_imported_reference_preserves_route_stop_relationships_and_dates():
    data = json.loads(Path('frontend/public/data/transit-reference.json').read_text())
    routes = {r['id']: r for r in data['routes']}
    assert data['kind'] == 'observed_agency_GTFS_reference_not_live_service'
    assert all(s['routes'] for s in data['stops'])
    assert all(f'{s["operator"]}:{rid}' in routes for s in data['stops'] for rid in s['routes'])
    assert len({s['id'] for s in data['stops']}) == len(data['stops'])
    assert all(37 < s['lat'] < 39 and -123 < s['lon'] < -121 for s in data['stops'])
    assert all(len(path) >= 2 for r in routes.values() for path in r['paths'])
    assert all(source['sha256'] and source['feed_end_date'] and source['license_url'] for source in data['sources'])
    assert any(r['operator'] == 'Muni' and r['short_name'] == '38' and r['paths'] for r in routes.values())
    assert any(s['operator'] == 'BART' and 'Antioch' in s['name'] for s in data['stops'])


def test_shape_simplification_keeps_endpoints_and_significant_bends():
    points = [[0, 0], [.1, 0], [.2, 0], [.2, .2], [.2, .3]]
    result = simplify(points, .01)
    assert result == [[0, 0], [.2, 0], [.2, .3]]
