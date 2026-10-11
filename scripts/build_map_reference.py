"""Transform agency GTFS into geographic reference and actual directed stop sequences.

No demand, current service availability, headway or travel-time claim is inferred.
"""

import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile


def simplify(points, tolerance=0.000035):
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    distances = []
    for point in points[1:-1]:
        t = (
            max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / den))
            if den
            else 0
        )
        distances.append(
            (point[0] - a[0] - t * dx) ** 2 + (point[1] - a[1] - t * dy) ** 2
        )
    maximum = max(distances, default=0)
    if maximum <= tolerance * tolerance:
        return [a, b]
    index = distances.index(maximum) + 1
    return simplify(points[: index + 1], tolerance)[:-1] + simplify(
        points[index:], tolerance
    )


def parse(path, operator, url):
    with ZipFile(path) as archive:

        def rows(name):
            if name not in archive.namelist():
                return iter(())
            return csv.DictReader(
                io.TextIOWrapper(archive.open(name), encoding="utf-8-sig")
            )

        routes = {row["route_id"]: row for row in rows("routes.txt")}
        trips = {row["trip_id"]: row for row in rows("trips.txt")}
        rawstops = {row["stop_id"]: row for row in rows("stops.txt")}

        def canonical(stop_id):
            stop = rawstops.get(stop_id, {})
            parent = stop.get("parent_station", "") if operator == "BART" else ""
            return parent or stop_id

        shape_routes, stop_routes = defaultdict(set), defaultdict(set)
        for trip in trips.values():
            shape_routes[trip.get("shape_id", "")].add(trip["route_id"])
        trip_counts = defaultdict(int)
        for row in rows("stop_times.txt"):
            trip = trips.get(row["trip_id"])
            if trip:
                stop_routes[canonical(row["stop_id"])].add(trip["route_id"])
                trip_counts[row["trip_id"]] += 1
        stops = []
        for stop_id, route_ids in stop_routes.items():
            stop = rawstops.get(stop_id)
            if not stop or not stop.get("stop_lat") or not stop.get("stop_lon"):
                continue
            stops.append(
                dict(
                    id=f"{operator}:{stop_id}",
                    name=stop["stop_name"],
                    lat=float(stop["stop_lat"]),
                    lon=float(stop["stop_lon"]),
                    operator=operator,
                    routes=sorted(route_ids),
                    rail=any(routes[r]["route_type"] != "3" for r in route_ids),
                )
            )
        valid_stop_ids = {stop["id"] for stop in stops}

        # Two streaming passes avoid retaining the 97MB Muni stop_times table in memory.
        longest_by_direction, longest_by_shape = {}, {}
        for trip_id, count in trip_counts.items():
            trip = trips[trip_id]
            direction_key = (trip["route_id"], trip.get("direction_id") or "0")
            variant_key = direction_key + (trip.get("shape_id", ""),)
            for table, key in [
                (longest_by_direction, direction_key),
                (longest_by_shape, variant_key),
            ]:
                existing = table.get(key)
                if existing is None or (count, trip_id) > (
                    trip_counts[existing],
                    existing,
                ):
                    table[key] = trip_id
        selected = set(longest_by_direction.values()) | set(longest_by_shape.values())
        sequence_rows = defaultdict(list)
        for row in rows("stop_times.txt"):
            if row["trip_id"] in selected:
                stop_id = f"{operator}:{canonical(row['stop_id'])}"
                if stop_id in valid_stop_ids:
                    sequence_rows[row["trip_id"]].append(
                        (int(row["stop_sequence"]), stop_id)
                    )
        sequences = {}
        for trip_id, sequence in sequence_rows.items():
            ordered = []
            for _, stop_id in sorted(sequence):
                if not ordered or stop_id != ordered[-1]:
                    ordered.append(stop_id)
            sequences[trip_id] = ordered

        shapes = defaultdict(list)
        for row in rows("shapes.txt"):
            if row["shape_id"] in shape_routes:
                shapes[row["shape_id"]].append(
                    (
                        int(row["shape_pt_sequence"]),
                        float(row["shape_pt_lat"]),
                        float(row["shape_pt_lon"]),
                    )
                )
        outputroutes = []
        for route_id, route in routes.items():
            geometries, path_keys, shape_indexes = [], {}, {}
            for shape_id in sorted(
                s for s, rs in shape_routes.items() if route_id in rs
            ):
                points = simplify(
                    [
                        [round(lat, 6), round(lon, 6)]
                        for _, lat, lon in sorted(shapes[shape_id])
                    ]
                )
                key = json.dumps(points)
                if len(points) > 1:
                    if key not in path_keys:
                        path_keys[key] = len(geometries)
                        geometries.append(points)
                    shape_indexes[shape_id] = path_keys[key]

            def make_sequence(direction, trip_id):
                trip = trips[trip_id]
                shape_id = trip.get("shape_id", "")
                return dict(
                    direction=direction,
                    trip_id=trip_id,
                    shape_id=shape_id,
                    path_index=shape_indexes.get(shape_id),
                    stop_ids=sequences.get(trip_id, []),
                )

            canonical_sequences = [
                make_sequence(direction, tid)
                for (rid, direction), tid in sorted(longest_by_direction.items())
                if rid == route_id
            ]
            variants = [
                make_sequence(direction, tid)
                for (rid, direction, shape), tid in sorted(longest_by_shape.items())
                if rid == route_id
            ]
            color = route.get("route_color", "").strip() or "75c7f2"
            outputroutes.append(
                dict(
                    id=f"{operator}:{route_id}",
                    feed_route_id=route_id,
                    operator=operator,
                    short_name=route["route_short_name"],
                    name=route["route_long_name"],
                    route_type=int(route["route_type"]),
                    color="#" + color,
                    paths=geometries,
                    stop_sequences=canonical_sequences,
                    service_variants=variants,
                    shape_path_indexes=shape_indexes,
                )
            )
        calendar, feed = list(rows("calendar.txt")), list(rows("feed_info.txt"))
        end = max((row.get("end_date", "") for row in calendar), default="")
        if feed:
            end = feed[0].get("feed_end_date") or end
        provenance = dict(
            operator=operator,
            url=url,
            sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            feed_end_date=end,
            stale_as_of_build=bool(
                end and end < datetime.now(timezone.utc).strftime("%Y%m%d")
            ),
            feed_info=feed,
            transformation="GTFS route/trip/stop-time joins; BART platforms grouped by parent station; all referenced shape variants simplified ~4m and rounded to 6 decimals. Longest trip per route/direction is canonical; longest per direction/shape preserves branches. Consecutive duplicate parent stops removed. No passenger demand inferred.",
            license_url=(
                "https://www.bart.gov/schedules/developers/developer-license-agreement"
                if operator == "BART"
                else "https://www.sfmta.com/reports/gtfs-transit-data"
            ),
        )
        return dict(stops=stops, routes=outputroutes, provenance=provenance)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--muni", required=True)
    parser.add_argument("--bart", required=True)
    parser.add_argument(
        "--output", default="frontend/public/data/transit-reference.json"
    )
    args = parser.parse_args()
    datasets = [
        parse(
            args.muni,
            "Muni",
            "https://muni-gtfs.apps.sfmta.com/data/muni_gtfs-current.zip",
        ),
        parse(
            args.bart, "BART", "https://www.bart.gov/dev/schedules/google_transit.zip"
        ),
    ]
    result = dict(
        kind="observed_agency_GTFS_reference_not_live_service",
        stops=sum((dataset["stops"] for dataset in datasets), []),
        routes=sum((dataset["routes"] for dataset in datasets), []),
        sources=[dataset["provenance"] for dataset in datasets],
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, separators=(",", ":")) + "\n")
    print(
        json.dumps(
            {
                "stops": len(result["stops"]),
                "routes": len(result["routes"]),
                "bytes": output.stat().st_size,
                "sources": [
                    (
                        dataset["provenance"]["operator"],
                        dataset["provenance"]["feed_end_date"],
                    )
                    for dataset in datasets
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
