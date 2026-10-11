"""Actual GTFS stop connectivity with explicitly synthetic city operating assumptions."""

from collections import defaultdict
from functools import lru_cache
import json
import math
from pathlib import Path

from .network import get_network

REFERENCE_PATH = (
    Path(__file__).resolve().parents[2] / "frontend/public/data/transit-reference.json"
)


def distance_meters(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(b["lon"] - a["lon"])
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371000 * 2 * math.asin(min(1, math.sqrt(value)))


def operating_assumptions(route):
    if route["operator"] == "BART":
        return (
            ("BART", 30, 60, 20) if route["route_type"] == 3 else ("BART", 15, 240, 45)
        )
    if route["route_type"] == 3:
        return (
            "Muni Bus",
            10 if route["short_name"] in {"1", "14", "14R", "38", "38R", "49"} else 15,
            55,
            12,
        )
    return (
        "Muni Metro",
        15 if route["route_type"] == 5 else 10,
        60 if route["route_type"] == 5 else 120,
        20,
    )


@lru_cache(maxsize=1)
def _get_city_network():
    reference = json.loads(REFERENCE_PATH.read_text())
    nodes = {}
    route_lookup = {route["id"]: route for route in reference["routes"]}
    for stop in reference["stops"]:
        routes = [
            route_lookup[f"{stop['operator']}:{rid}"]
            for rid in stop["routes"]
            if f"{stop['operator']}:{rid}" in route_lookup
        ]
        operators = sorted({operating_assumptions(route)[0] for route in routes})
        nodes[stop["id"]] = dict(
            stop,
            operator=operators[0] if operators else stop["operator"],
            operators=operators,
            routes=[route["id"] for route in routes],
            provenance="Observed agency GTFS stop coordinates and route membership",
        )
    edges = {}
    for route in reference["routes"]:
        operator, headway, capacity, speed = operating_assumptions(route)
        sequences = route.get("stop_sequences", []) + route.get("service_variants", [])
        for sequence in sequences:
            stop_ids = sequence["stop_ids"]
            cumulative_minutes = 0
            for source, target in zip(stop_ids, stop_ids[1:]):
                if source == target or source not in nodes or target not in nodes:
                    continue
                edge_id = (
                    f"city:{route['id']}:{sequence['direction']}:{source}>{target}"
                )
                length = distance_meters(nodes[source], nodes[target])
                travel = max(1, math.ceil(length / (speed * 1000 / 60) + 0.5))
                departure_offset = cumulative_minutes % headway
                cumulative_minutes += travel
                if edge_id in edges:
                    continue
                edges[edge_id] = dict(
                    id=edge_id,
                    source=source,
                    target=target,
                    operator=operator,
                    service=route["short_name"],
                    route_id=route["id"],
                    direction=sequence["direction"],
                    shape_id=sequence["shape_id"],
                    path_index=sequence["path_index"],
                    travel_minutes=travel,
                    headway_minutes=headway,
                    departure_offset_minutes=departure_offset,
                    capacity=capacity,
                    distance_meters=round(length, 1),
                    provenance="Observed consecutive GTFS stops; synthetic speed/dwell/headway/capacity",
                    geometry={
                        "route_id": route["id"],
                        "path_index": sequence["path_index"],
                        "shape_id": sequence["shape_id"],
                    },
                )
    compact = get_network()
    for node in compact["nodes"]:
        if node["operator"] == "Caltrain":
            nodes[node["id"]] = dict(
                node,
                operators=["Caltrain"],
                routes=["Caltrain:SF-Millbrae"],
                provenance="Derived selected-station coordinates; synthetic service",
            )
    for edge in compact["edges"]:
        if edge["operator"] == "Caltrain":
            caltrain_offsets = {
                "sf_caltrain-22nd": 0,
                "22nd-bayshore": 5,
                "bayshore-millbrae_caltrain": 15,
                "millbrae_caltrain-bayshore": 0,
                "bayshore-22nd": 20,
                "22nd-sf_caltrain": 0,
            }
            edges[edge["id"]] = dict(
                edge,
                route_id="Caltrain:SF-Millbrae",
                departure_offset_minutes=caltrain_offsets[edge["id"]],
                direction="selected",
                provenance="Synthetic selected real Caltrain corridor connections",
            )
    # Bounded nearby interchange edges. Route edges always come from stop_times.
    # The walk grid uses ~110m cells and checks exact geodesic distance <=100m.
    grid = defaultdict(list)
    for node in nodes.values():
        grid[
            (math.floor(node["lat"] / 0.001), math.floor(node["lon"] / 0.0013))
        ].append(node)
    candidates = []
    for node in nodes.values():
        cell = (math.floor(node["lat"] / 0.001), math.floor(node["lon"] / 0.0013))
        for lat_offset in [-1, 0, 1]:
            for lon_offset in [-1, 0, 1]:
                for other in grid.get((cell[0] + lat_offset, cell[1] + lon_offset), []):
                    if node["id"] >= other["id"]:
                        continue
                    distance = distance_meters(node, other)
                    if distance > 100:
                        continue
                    # Stops with identical route membership already have actual service connectivity.
                    if set(node["routes"]) == set(other["routes"]):
                        continue
                    cross_operator = not set(node["operators"]) & set(
                        other["operators"]
                    )
                    score = distance + (0 if cross_operator else 50)
                    candidates.append((score, node["id"], other["id"], distance))
    walking_degree = defaultdict(int)
    for _, left, right, distance in sorted(candidates):
        if walking_degree[left] >= 3 or walking_degree[right] >= 3:
            continue
        walking_degree[left] += 1
        walking_degree[right] += 1
        for source, target in [(left, right), (right, left)]:
            edge_id = f"city:walk:{source}>{target}"
            # Five minutes includes finding the platform and fare gates; distance is not a straight-line transit service.
            edges[edge_id] = dict(
                id=edge_id,
                source=source,
                target=target,
                operator="walk",
                service="walk",
                route_id="walking-transfer",
                travel_minutes=5,
                headway_minutes=1,
                departure_offset_minutes=0,
                capacity=10000,
                distance_meters=round(distance, 1),
                provenance="Estimated pedestrian transfer <=100m straight-line; no surveyed entrance/accessible pathway guarantee",
            )
    node_list = list(nodes.values())
    for node in node_list:
        node["queue_area_id"] = node["id"]
        node["queue_area_name"] = node["name"]
    edge_list = list(edges.values())
    connected = set()
    for edge in edge_list:
        connected.update((edge["source"], edge["target"]))
    return dict(
        nodes=node_list,
        edges=edge_list,
        routes=reference["routes"],
        demand_clusters=[
            {"name": name, "lat": lat, "lon": lon} for name, lat, lon in CLUSTERS
        ],
        time_step_minutes=1,
        end_minute=180,
        start_hour=16,
        resource_limits={"Muni Bus": 12, "Muni Metro": 4, "BART": 2, "Caltrain": 1},
        provenance={
            "kind": "Observed GTFS topology with synthetic operations and synthetic commute demand",
            "sources": reference["sources"],
            "reference_file": "frontend/public/data/transit-reference.json",
            "served_stops": len(nodes),
            "connected_stops": len(connected),
            "walking": "At most3 transfer neighbors per stop; distance<=100m; straight-line proximity, not verified accessibility",
            "operations": "Directed segment departures offset by cumulative representative-route travel time; synthetic headways/capacity; travel = ceil(geodesic distance/assumed speed +0.5min dwell), minimum1min. Bus12kph, Muni rail20kph, BART45kph. No observed live vehicle or passenger demand.",
            "caltrain": "Selected four-node corridor retained from compact synthetic model; not full Caltrain GTFS",
            "route_variants": "Canonical longest trip per direction; actual additional longest trip per direction/shape preserves GTFS branches. Variant edges share route IDs; variants are not additional fleet. Repeated loop edges use first-occurrence departure phase (one canonical route36 edge); alternate branches share canonical segment phases.",
        },
    )


def get_city_network(horizon_minutes=180):
    """Reuse observed topology; duration is an explicit synthetic scenario parameter."""
    if (
        not isinstance(horizon_minutes, int)
        or isinstance(horizon_minutes, bool)
        or not 180 <= horizon_minutes <= 1440
    ):
        raise ValueError("horizon_minutes must be an integer from180 to1440")
    return dict(
        _get_city_network(),
        end_minute=horizon_minutes,
        horizon_minutes=horizon_minutes,
        start_time="16:00",
        supported_horizon_minutes={"minimum": 180, "maximum": 1440},
    )


CLUSTERS = [
    ("Richmond", 37.780, -122.478),
    ("Outer Richmond", 37.777, -122.495),
    ("Sunset", 37.754, -122.490),
    ("Inner Sunset", 37.762, -122.466),
    ("Parkside", 37.739, -122.482),
    ("Lakeshore", 37.725, -122.488),
    ("Excelsior", 37.723, -122.435),
    ("Ingleside", 37.722, -122.455),
    ("Bayview", 37.733, -122.390),
    ("Visitacion Valley", 37.714, -122.410),
    ("Portola", 37.727, -122.405),
    ("Mission", 37.752, -122.418),
    ("Noe Valley", 37.750, -122.433),
    ("Castro", 37.761, -122.435),
    ("Marina", 37.801, -122.439),
    ("Pacific Heights", 37.792, -122.435),
    ("Haight", 37.770, -122.447),
    ("Western Addition", 37.781, -122.433),
    ("Hayes Valley", 37.776, -122.424),
    ("North Beach", 37.800, -122.410),
    ("Chinatown", 37.795, -122.407),
    ("Potrero Hill", 37.759, -122.400),
    ("Dogpatch", 37.758, -122.389),
    ("Bernal Heights", 37.739, -122.416),
    ("Glen Park", 37.733, -122.433),
    ("Oakland", 37.804, -122.271),
    ("Daly City", 37.706, -122.469),
]

# Synthetic job/activity centers. Several stops per center spread arrivals across the network.
DESTINATIONS = [
    ("Financial District", 37.793, -122.398),
    ("Union Square", 37.788, -122.407),
    ("Civic Center", 37.779, -122.414),
    ("SoMa", 37.784, -122.401),
    ("Mission Bay", 37.770, -122.391),
    ("Embarcadero", 37.795, -122.394),
    ("UCSF Parnassus", 37.763, -122.458),
    ("SF State", 37.722, -122.478),
    ("Downtown Oakland", 37.803, -122.271),
]


def _largest_strongly_connected(nodes, edges):
    """Stops reachable from and back to each other, so every commute can return."""
    forward, backward = defaultdict(list), defaultdict(list)
    for edge in edges:
        forward[edge["source"]].append(edge["target"])
        backward[edge["target"]].append(edge["source"])
    order, seen = [], set()
    for start in sorted(nodes):
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, iter(forward[start]))]
        while stack:
            node, children = stack[-1]
            child = next((c for c in children if c not in seen), None)
            if child is None:
                stack.pop()
                order.append(node)
            else:
                seen.add(child)
                stack.append((child, iter(forward[child])))
    assigned, best = set(), set()
    for start in reversed(order):
        if start in assigned:
            continue
        component, pending = set(), [start]
        assigned.add(start)
        while pending:
            node = pending.pop()
            component.add(node)
            for parent in backward[node]:
                if parent not in assigned:
                    assigned.add(parent)
                    pending.append(parent)
        if len(component) > len(best):
            best = component
    return best


def _spread_stops(candidates, lat, lon, count, spacing_m, pool):
    """Nearest connected stops to a point, at least spacing_m apart."""
    point = {"lat": lat, "lon": lon}
    chosen = []
    for node in sorted(candidates, key=lambda n: distance_meters(n, point))[:pool]:
        if all(distance_meters(node, other) >= spacing_m for other in chosen):
            chosen.append(node)
        if len(chosen) == count:
            break
    return chosen


@lru_cache(maxsize=1)
def get_city_demand_pairs():
    """Neighborhood↔job-center OD samples over many stops; demand weights are synthetic."""
    network = get_city_network()
    nodes = {node["id"]: node for node in network["nodes"]}
    connected = _largest_strongly_connected(nodes, network["edges"])
    candidates = [nodes[node_id] for node_id in sorted(connected)]
    centers = [(name, _spread_stops(candidates, lat, lon, 4, 150, 40)) for name, lat, lon in DESTINATIONS]
    results = []
    for cluster_index, (cluster, lat, lon) in enumerate(CLUSTERS):
        homes = _spread_stops(candidates, lat, lon, 4, 250, 60)
        if not homes:
            continue
        for center_index, (downtown, targets) in enumerate(centers):
            if not targets:
                continue
            origin = homes[center_index % len(homes)]
            destination = targets[cluster_index % len(targets)]
            if origin["id"] == destination["id"]:
                continue
            for source, target, direction in [
                (origin, destination, "inbound"),
                (destination, origin, "outbound"),
            ]:
                results.append(
                    dict(
                        origin=source["id"],
                        destination=target["id"],
                        cluster=cluster,
                        downtown=downtown,
                        direction=direction,
                        weight=1,
                        origin_name=source["name"],
                        destination_name=target["name"],
                        provenance="Synthetic residential commute OD spread over several connected observed GTFS stops per neighborhood and job center",
                    )
                )
    # Include route-local commute cohorts so every published bus/rail route can carry demand.
    # These are generated weekday OD assumptions, not ridership inferred from GTFS.
    for route in network["routes"]:
        for sequence in route.get("stop_sequences", []):
            stop_ids = sequence["stop_ids"]
            if len(stop_ids) < 2:
                continue
            origin_index = min(len(stop_ids) - 2, len(stop_ids) // 4)
            destination_index = max(1, (len(stop_ids) * 3) // 4)
            origin = stop_ids[origin_index]
            destination = stop_ids[destination_index]
            route_path = [
                f"city:{route['id']}:{sequence['direction']}:{source}>{target}"
                for source, target in zip(
                    stop_ids[origin_index:destination_index],
                    stop_ids[origin_index + 1 : destination_index + 1],
                )
                if source != target
            ]
            if origin == destination:
                continue
            results.append(
                dict(
                    origin=origin,
                    destination=destination,
                    cluster=f"Route {route['short_name']} corridor",
                    downtown="Along published route",
                    direction=sequence["direction"],
                    weight=0.25,
                    route_id=route["id"],
                    path=route_path,
                    origin_name=nodes[origin]["name"],
                    destination_name=nodes[destination]["name"],
                    provenance="Synthetic OD along canonical actual GTFS route to exercise citywide services",
                )
            )
    return results
