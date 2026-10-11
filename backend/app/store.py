"""Atlas system of record. Offline store is explicit and never reports Atlas health."""
import copy
import os
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
import certifi

load_dotenv()


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    collections = ('transit_nodes', 'transit_connections', 'scenarios', 'simulation_runs',
                   'simulation_frames', 'agent_traces', 'harness_versions', 'mutation_proposals',
                   'evaluation_results', 'deployment_decisions', 'agent_memory', 'control', 'jobs')

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
        load_dotenv(override=True)
        uri = os.getenv('MONGODB_URI', '')
        if not uri:
            self.error = 'MONGODB_URI missing: provide the organizer Atlas Sandbox credential.'
            raise RuntimeError(self.error)
        # Never provision or fall back to a different/local database.
        try:
            if self.client is None:
                self.client = MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000,
                                          tlsCAFile=certifi.where() if uri.startswith('mongodb+srv://') else None)
            self.client.admin.command('ping')
            self.db = self.client[os.getenv('MONGODB_DB', 'bayflow')]
            probe = {'_id': str(uuid4()), 'created_at': now(), 'kind': 'connectivity_read_write_probe'}
            self.db['control'].insert_one(probe)
            read = self.db['control'].find_one({'_id': probe['_id']})
            if read is None or read['kind'] != probe['kind']:
                raise RuntimeError('Read-after-write verification failed')
            self.db['control'].delete_one({'_id': probe['_id']})
            for collection in self.collections:
                self.db[collection].create_index([('created_at', ASCENDING)])
            self.db.simulation_frames.create_index([('run_id', ASCENDING), ('minute', ASCENDING)])
            self.db.agent_traces.create_index([('run_id', ASCENDING)])
            self.error = None
        except Exception as exc:
            # Driver errors can contain hosts/URIs; expose only the exception class.
            detail = str(exc).lower()
            if 'certificate_verify_failed' in detail or 'certificate verify failed' in detail:
                hint = 'TLS certificate validation failed. Install/update trusted CA certificates; TLS verification remains enabled.'
            elif 'authentication failed' in detail or type(exc).__name__ == 'OperationFailure':
                hint = 'Check the organizer username/password and database permissions.'
            elif 'operation not permitted' in detail:
                hint = 'This process is blocked by the session network sandbox; run verification from your terminal.'
            elif 'timed out' in detail or 'timeout' in type(exc).__name__.lower():
                hint = 'Cluster hosts did not respond. Check the Atlas IP access list, cluster availability, VPN/firewall and TCP port 27017.'
            else:
                hint = 'Check the organizer connection string, DNS and network allowlist.'
            self.error = f'Atlas ping/read/write failed ({type(exc).__name__}). {hint}'
            raise RuntimeError(self.error) from None

    def ensure(self):
        if not self.offline and self.db is None:
            self.connect()

    def put(self, collection, key, document):
        self.ensure()
        doc = copy.deepcopy(document)
        doc['_id'] = key
        doc.setdefault('created_at', now())
        with self.lock:
            if self.offline:
                self.memory[collection][key] = doc
            else:
                self.db[collection].replace_one({'_id': key}, doc, upsert=True)
        return doc

    def get(self, collection, key):
        self.ensure()
        with self.lock:
            doc = self.memory[collection].get(key) if self.offline else self.db[collection].find_one({'_id': key})
            return copy.deepcopy(doc)

    def list(self, collection, query=None, limit=100):
        self.ensure()
        with self.lock:
            if self.offline:
                docs = list(self.memory[collection].values())
                if query:
                    docs = [d for d in docs if all(d.get(k) == v for k, v in query.items())]
                return copy.deepcopy(docs[-limit:])
            return list(self.db[collection].find(query or {}).sort('created_at', 1).limit(limit))

    def save_run(self, run):
        run_id = run['run_id']
        summary = {k: v for k, v in run.items() if k not in ('frames', 'traces')}
        summary['frame_count'] = len(run['frames'])
        summary['trace_count'] = len(run['traces'])
        summary['status'] = 'persisting'
        self.put('simulation_runs', run_id, summary)
        frames = [dict(frame, _id=f'{run_id}:{i}', run_id=run_id, created_at=now()) for i, frame in enumerate(run['frames'])]
        traces = [dict(trace, _id=f'{run_id}:{i}', run_id=run_id, created_at=now()) for i, trace in enumerate(run['traces'])]
        if self.offline:
            for collection, docs in [('simulation_frames', frames), ('agent_traces', traces)]:
                for doc in docs:
                    self.put(collection, doc['_id'], doc)
        else:
            if frames:
                self.db.simulation_frames.insert_many(frames)
            if traces:
                self.db.agent_traces.insert_many(traces)
        summary['status'] = 'completed'
        self.put('simulation_runs', run_id, summary)
        return summary

    def status(self):
        if self.offline:
            return {'connected': False, 'mode': 'offline', 'eligible': False, 'error': 'Explicit in-memory preview; no Atlas persistence.', 'counts': {k: len(v) for k, v in self.memory.items()}}
        try:
            self.connect() if self.db is None else self.client.admin.command('ping')
            return {'connected': True, 'mode': 'atlas', 'eligible': True, 'database': self.db.name,
                    'verified_read_write': True, 'counts': {k: self.db[k].estimated_document_count() for k in self.collections}}
        except Exception:
            return {'connected': False, 'mode': 'atlas_required', 'eligible': False, 'error': self.error or 'Atlas connection unavailable', 'counts': {}}
