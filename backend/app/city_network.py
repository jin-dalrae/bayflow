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
def get_city_network():
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


CLUSTERS = [
    ("Richmond", 37.780, -122.478),
    ("Sunset", 37.754, -122.490),
    ("Parkside", 37.739, -122.482),
    ("Excelsior", 37.723, -122.435),
    ("Bayview", 37.733, -122.390),
    ("Visitacion Valley", 37.714, -122.410),
    ("Mission", 37.752, -122.418),
    ("Noe Valley", 37.750, -122.433),
    ("Marina", 37.801, -122.439),
    ("Haight", 37.770, -122.447),
    ("Bernal Heights", 37.739, -122.416),
    ("Glen Park", 37.733, -122.433),
    ("Oakland", 37.804, -122.271),
    ("Daly City", 37.706, -122.469),
]


@lru_cache(maxsize=1)
def get_city_demand_pairs():
    """Connected neighborhood↔downtown OD samples; demand weights are synthetic."""
    network = get_city_network()
    nodes = {node["id"]: node for node in network["nodes"]}
    adjacency = defaultdict(list)
    for edge in network["edges"]:
        adjacency[edge["source"]].append(
            (
                edge["target"],
                edge["travel_minutes"]
                + (0 if edge["operator"] == "walk" else edge["headway_minutes"] / 2),
            )
        )
    destination_points = [
        ("Financial District", 37.793, -122.398),
        ("Civic Center", 37.779, -122.414),
        ("Mission Bay", 37.770, -122.391),
    ]
    destinations = []
    for name, lat, lon in destination_points:
        candidates = sorted(
            (node for node in nodes.values() if node["id"] in adjacency),
            key=lambda node: distance_meters(node, {"lat": lat, "lon": lon}),
        )[:10]
        destinations.append((name, candidates))

    def reachable(origin):
        visited = set()
        pending = [origin]
        while pending:
            node = pending.pop()
            if node in visited:
                continue
            visited.add(node)
            pending.extend(
                target for target, _ in adjacency[node] if target not in visited
            )
        return visited

    results = []
    for cluster, lat, lon in CLUSTERS:
        candidates = sorted(
            (node for node in nodes.values() if node["id"] in adjacency),
            key=lambda node: distance_meters(node, {"lat": lat, "lon": lon}),
        )[:12]
        for downtown, targets in destinations:
            selected = None
            for origin in candidates:
                connected = reachable(origin["id"])
                for destination in targets:
                    if destination["id"] in connected and origin["id"] in reachable(
                        destination["id"]
                    ):
                        selected = (origin, destination)
                        break
                if selected:
                    break
            if not selected:
                continue
            origin, destination = selected
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
                        provenance="Synthetic residential commute OD mapped to geographically nearest connected observed GTFS stops",
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
