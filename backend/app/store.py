"""Atlas system of record. Offline store is explicit and never reports Atlas health."""

import copy
import json
import zlib
import os
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, ReplaceOne
import certifi

load_dotenv()


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    collections = (
        "transit_nodes",
        "transit_connections",
        "scenarios",
        "simulation_runs",
        "simulation_frames",
        "agent_traces",
        "harness_versions",
        "mutation_proposals",
        "evaluation_results",
        "deployment_decisions",
        "agent_memory",
        "control",
        "jobs",
    )

    def __init__(self, offline=False):
        self.offline = offline
        self.db = None
        self.client = None
        self.error = None
        self.lock = RLock()
        self.memory = {name: {} for name in self.collections}

    def connect(self):
        if self.offline:
            return
        load_dotenv(override=False)
        uri = os.getenv("MONGODB_URI", "")
        if not uri:
            self.error = (
                "MONGODB_URI missing: provide the organizer Atlas Sandbox credential."
            )
            raise RuntimeError(self.error)
        # Never provision or fall back to a different/local database.
        try:
            if self.client is None:
                self.client = MongoClient(
                    uri,
                    serverSelectionTimeoutMS=10000,
                    connectTimeoutMS=10000,
                    tlsCAFile=(
                        certifi.where() if uri.startswith("mongodb+srv://") else None
                    ),
                )
            self.client.admin.command("ping")
            database = self.client[os.getenv("MONGODB_DB", "bayflow")]
            probe = {
                "_id": str(uuid4()),
                "created_at": now(),
                "kind": "connectivity_read_write_probe",
            }
            database["control"].insert_one(probe)
            read = database["control"].find_one({"_id": probe["_id"]})
            if read is None or read["kind"] != probe["kind"]:
                raise RuntimeError("Read-after-write verification failed")
            database["control"].delete_one({"_id": probe["_id"]})
            for collection in self.collections:
                database[collection].create_index([("created_at", ASCENDING)])
            database.simulation_frames.create_index(
                [("run_id", ASCENDING), ("minute", ASCENDING)]
            )
            database.agent_traces.create_index([("run_id", ASCENDING)])
            self.db = database
            self.error = None
        except Exception as exc:
            # A ping alone never establishes usable persistence. Any failed
            # read/write/index verification leaves the official path disabled.
            self.db = None
            # Driver errors can contain hosts/URIs; expose only the exception class.
            detail = str(exc).lower()
            if (
                "certificate_verify_failed" in detail
                or "certificate verify failed" in detail
            ):
                hint = "TLS certificate validation failed. Install/update trusted CA certificates; TLS verification remains enabled."
            elif (
                "authentication failed" in detail
                or type(exc).__name__ == "OperationFailure"
            ):
                hint = "Check the organizer username/password and database permissions."
            elif "operation not permitted" in detail:
                hint = "This process is blocked by the session network sandbox; run verification from your terminal."
            elif "timed out" in detail or "timeout" in type(exc).__name__.lower():
                hint = "Cluster hosts did not respond. Check the Atlas IP access list, cluster availability, VPN/firewall and TCP port 27017."
            else:
                hint = (
                    "Check the organizer connection string, DNS and network allowlist."
                )
            self.error = f"Atlas ping/read/write failed ({type(exc).__name__}). {hint}"
            raise RuntimeError(self.error) from None

    def ensure(self):
        if not self.offline and self.db is None:
            self.connect()

    def put(self, collection, key, document):
        self.ensure()
        doc = copy.deepcopy(document)
        doc["_id"] = key
        doc.setdefault("created_at", now())
        with self.lock:
            if self.offline:
                self.memory[collection][key] = doc
            else:
                self.db[collection].replace_one({"_id": key}, doc, upsert=True)
        return doc

    def put_many(self, collection, documents):
        self.ensure()
        docs=[dict(copy.deepcopy(d), _id=d["id"], created_at=now()) for d in documents]
        with self.lock:
            if self.offline:
                self.memory[collection].update({d["_id"]:d for d in docs})
            elif docs:
                self.db[collection].bulk_write([ReplaceOne({"_id":d["_id"]},d,upsert=True) for d in docs],ordered=False)

    def get(self, collection, key):
        self.ensure()
        with self.lock:
            doc = (
                self.memory[collection].get(key)
                if self.offline
                else self.db[collection].find_one({"_id": key})
            )
            return self.decode_document(copy.deepcopy(doc)) if doc else None

    @staticmethod
    def decode_document(doc):
        if doc.get("encoding") == "json-zlib-v1":
            payload=json.loads(zlib.decompress(doc["payload"]))
            return dict(payload, **{k:v for k,v in doc.items() if k not in ("payload","encoding")})
        return doc

    def list(self, collection, query=None, limit=100):
        self.ensure()
        with self.lock:
            if self.offline:
                docs = list(self.memory[collection].values())
                if query:
                    docs = [
                        d for d in docs if all(d.get(k) == v for k, v in query.items())
                    ]
                return [self.decode_document(d) for d in copy.deepcopy(docs[-limit:])]
            return [self.decode_document(d) for d in self.db[collection].find(query or {}).sort("created_at", 1).limit(limit)]

    def save_run(self, run):
        run_id = run["run_id"]
        summary = {k: v for k, v in run.items() if k not in ("frames", "traces")}
        summary["frame_count"] = len(run["frames"])
        summary["trace_count"] = len(run["traces"])
        summary["status"] = "persisting"
        self.put("simulation_runs", run_id, summary)
        frames = [
            dict(frame, _id=f"{run_id}:{i}", run_id=run_id, created_at=now())
            for i, frame in enumerate(run["frames"])
        ]
        traces = [
            dict(trace, _id=f"{run_id}:{i}", run_id=run_id, created_at=now())
            for i, trace in enumerate(run["traces"])
        ]
        if self.offline:
            for collection, docs in [
                ("simulation_frames", frames),
                ("agent_traces", traces),
            ]:
                for doc in docs:
                    self.put(collection, doc["_id"], doc)
        else:
            if frames:
                # Lossless encoding keeps full city passenger proof in the shared sandbox.
                if run.get("scenario")=="city_commute":
                    frames=[dict(_id=f["_id"],run_id=run_id,minute=f["minute"],time=f["time"],created_at=f["created_at"],passenger_balance=f["passenger_balance"],encoding="json-zlib-v1",payload=zlib.compress(json.dumps(f,separators=(",",":")).encode(),6)) for f in frames]
                    summary["frame_encoding"]="json-zlib-v1"
                    summary["compressed_frame_bytes"]=sum(len(f["payload"]) for f in frames)
                self.db.simulation_frames.insert_many(frames)
            if traces:
                self.db.agent_traces.insert_many(traces)
        summary["status"] = "completed"
        self.put("simulation_runs", run_id, summary)
        return summary

    def status(self):
        if self.offline:
            return {
                "connected": False,
                "mode": "offline",
                "eligible": False,
                "error": "Explicit in-memory preview; no Atlas persistence.",
                "counts": {k: len(v) for k, v in self.memory.items()},
            }
        try:
            self.connect() if self.db is None else self.client.admin.command("ping")
            return {
                "connected": True,
                "mode": "atlas",
                "eligible": True,
                "database": self.db.name,
                "verified_read_write": True,
                "counts": {
                    k: self.db[k].estimated_document_count() for k in self.collections
                },
            }
        except Exception:
            return {
                "connected": False,
                "mode": "atlas_required",
                "eligible": False,
                "error": self.error or "Atlas connection unavailable",
                "counts": {},
            }
