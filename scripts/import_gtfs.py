#!/usr/bin/env python3
"""Import an optional 511 GTFS corridor slice without changing the demo model.

No archive extraction, executable feed content, or credentials are persisted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zipfile import ZipFile

from dotenv import load_dotenv
from pymongo import MongoClient, ReplaceOne

MAX_BYTES = 300 * 1024 * 1024
CORRIDOR = (37.58, 37.84, -122.53, -122.22)


def rows(archive: ZipFile, filename: str):
    matches = [name for name in archive.namelist() if Path(name).name == filename]
    if not matches:
        return
    member = archive.getinfo(matches[0])
    if member.file_size > MAX_BYTES:
        raise ValueError(f"GTFS member too large: {filename}")
    with archive.open(member) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))


def inside(row):
    try:
        lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
        south, north, west, east = CORRIDOR
        return south <= lat <= north and west <= lon <= east
    except (ValueError, KeyError, TypeError):
        return False


def parse(blob: bytes):
    with ZipFile(io.BytesIO(blob)) as archive:
        stops = [r for r in rows(archive, "stops.txt") if inside(r)]
        if not stops:
            raise ValueError("No valid corridor stops found in stops.txt")
        stop_ids = {r["stop_id"] for r in stops}
        stop_times = [r for r in rows(archive, "stop_times.txt") if r.get("stop_id") in stop_ids]
        trip_ids = {r["trip_id"] for r in stop_times}
        trips = [r for r in rows(archive, "trips.txt") if r.get("trip_id") in trip_ids]
        route_ids = {r["route_id"] for r in trips}
        service_ids = {r["service_id"] for r in trips}
        shape_ids = {r.get("shape_id") for r in trips} - {None, ""}
        routes = [r for r in rows(archive, "routes.txt") if r.get("route_id") in route_ids]
        agency_ids = {r.get("agency_id") for r in routes}
        return {
            "stops": stops,
            "stop_times": stop_times,
            "trips": trips,
            "routes": routes,
            "agency": [r for r in rows(archive, "agency.txt") if not agency_ids or r.get("agency_id") in agency_ids or "" in agency_ids],
            "calendar": [r for r in rows(archive, "calendar.txt") if r.get("service_id") in service_ids],
            "calendar_dates": [r for r in rows(archive, "calendar_dates.txt") if r.get("service_id") in service_ids],
            "shapes": [r for r in rows(archive, "shapes.txt") if r.get("shape_id") in shape_ids],
            "transfers": [r for r in rows(archive, "transfers.txt") if r.get("from_stop_id") in stop_ids and r.get("to_stop_id") in stop_ids],
        }


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, help="Previously downloaded official GTFS ZIP")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only; no database writes")
    args = parser.parse_args()
    if args.zip:
        if args.zip.stat().st_size > MAX_BYTES:
            raise SystemExit("ZIP exceeds size limit")
        blob = args.zip.read_bytes()
        source = "user_supplied_gtfs_zip; verify publisher before presentation"
    else:
        token = os.getenv("TRANSIT_511_API_KEY")
        if not token:
            raise SystemExit("Set TRANSIT_511_API_KEY or provide --zip. No feed was imported.")
        url = "https://api.511.org/transit/datafeeds?" + urlencode({"api_key": token, "operator_id": "RG"})
        try:
            with urlopen(url, timeout=90) as response:
                blob = response.read(MAX_BYTES + 1)
        except Exception:
            raise SystemExit("511 download failed. Check your token/access; credential-bearing URL suppressed.") from None
        if len(blob) > MAX_BYTES:
            raise SystemExit("Download exceeds size limit")
        source = "https://api.511.org/transit/datafeeds (operator_id=RG; credential omitted)"
    tables = parse(blob)
    import_id = hashlib.sha256(blob).hexdigest()
    provenance = {
        "_id": import_id,
        "source": source,
        "data_class": "user_supplied_unverified_gtfs" if args.zip else "observed_published_schedule",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "sha256": import_id,
        "counts": {name: len(table) for name, table in tables.items()},
        "transform": "geographic corridor stops; associated trip/route/service/shape rows; in-corridor transfers",
        "bounding_box": list(CORRIDOR),
        "attribution": "data provided by 511.org",
        "terms": "https://511.org/sites/default/files/2026-04/511_Data_Agreement_Final_2026.pdf",
        "runtime_model_changed": False,
    }
    if not args.dry_run:
        uri = os.getenv("MONGODB_URI", "")
        if not uri:
            raise SystemExit("MONGODB_URI must be the organizer-provided Atlas Sandbox; no substitute is created.")
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        database = client[os.getenv("MONGODB_DB", "bayflow")]
        for name, table in tables.items():
            collection = database[f"gtfs_{name}"]
            collection.create_index("import_id")
            for start in range(0, len(table), 1000):
                batch = table[start:start + 1000]
                writes = []
                for offset, row in enumerate(batch, start=start):
                    doc = {**row, "import_id": import_id, "_id": f"{import_id}:{offset}"}
                    writes.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
                if writes:
                    collection.bulk_write(writes, ordered=False)
        database.gtfs_imports.replace_one({"_id": import_id}, provenance, upsert=True)
        if not database.gtfs_imports.find_one({"_id": import_id}):
            raise RuntimeError("Import provenance read-back failed")
        client.close()
    print(json.dumps({**provenance, "dry_run": args.dry_run}, indent=2))


if __name__ == "__main__":
    main()
