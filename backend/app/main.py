"""BayFlow local control API: real simulation jobs and Atlas-backed harness lifecycle."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from .store import Store, now
from .network import get_network
from .models import HarnessConfig
from .evolution import current_config, execute_run, evolve

app = FastAPI(title='BayFlow', version='0.1.0', description='Self-evolving multi-agent transit harness')
app.add_middleware(CORSMiddleware, allow_origin_regex=r'http://(localhost|127\.0\.0\.1):517[0-9]', allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
atlas = Store()
offline_store = Store(offline=True)
jobs = {}
jobs_lock = threading.RLock()
evolution_lock = threading.Lock()
pool = ThreadPoolExecutor(max_workers=2)

SCENARIOS = [
    {'id': 'event_surge', 'name': 'The Bay Area Event Surge', 'description': 'Synthetic overlapping stadium departures, driver loss and BART delay.', 'synthetic': True, 'start_time': '16:00', 'end_time': '23:00', 'events': [
        {'minute': 80, 'time': '17:20', 'name': 'Muni driver unavailable'}, {'minute': 130, 'time': '18:10', 'name': 'BART service delay'},
        {'minute': 285, 'time': '20:45', 'name': 'Fictional Chase Center event ends'}, {'minute': 330, 'time': '21:30', 'name': 'Fictional Oracle Park event ends'}, {'minute': 360, 'time': '22:00', 'name': 'Observe cascading queues and missed transfers'}]},
    {'id': 'commuter', 'name': 'Commuter Control', 'description': 'Synthetic weekday demand without event surges; regression gate.', 'synthetic': True},
    {'id': 'accident', 'name': 'Mission Bay Interruption', 'description': 'Synthetic accident blocks a Muni segment in addition to event surges.', 'synthetic': True}]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['static', 'fixed', 'evolving'] = 'fixed'
    seed: int = Field(default=42, ge=0, le=1_000_000)
    scenario: Literal['event_surge', 'commuter', 'accident'] = 'event_surge'
    offline: bool = False


class EvolveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    seed: int = Field(default=42, ge=0, le=1_000_000)
    iterations: int = Field(default=2, ge=1, le=4)
    offline: bool = False
    use_llm: bool = True


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = Field(pattern=r'^v[0-9]+$')
    offline: bool = False


def select_store(offline=False, required=True):
    store = offline_store if offline or os.getenv('BAYFLOW_OFFLINE') == '1' else atlas
    if required:
        try:
            store.ensure()
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from None
    return store


def seed_store(store):
    if store.get('scenarios', 'event_surge'):
        return
    network = get_network()
    for node in network['nodes']:
        store.put('transit_nodes', node['id'], dict(node, provenance=network['provenance']))
    for edge in network['edges']:
        store.put('transit_connections', edge['id'], dict(edge, provenance=network['provenance']))
    for scenario in SCENARIOS:
        store.put('scenarios', scenario['id'], scenario)
    current_config(store)


def submit(store, kind, operation):
    job_id = str(uuid4())
    job = {'job_id': job_id, 'kind': kind, 'status': 'pending', 'stage': 'Queued', 'history': [], 'created_at': now(), 'persistence': 'offline_preview' if store.offline else 'atlas'}
    with jobs_lock:
        jobs[job_id] = job

    def progress(stage):
        with jobs_lock:
            job['stage'] = stage
            job['history'].append({'stage': stage, 'at': now()})
            store.put('jobs', job_id, {k: v for k, v in job.items() if k != 'result'})

    def worker():
        try:
            job['status'] = 'running'
            seed_store(store)
            progress('Starting backend operation')
            result = operation(progress)
            with jobs_lock:
                job.update(status='completed', stage='Complete', result=result, completed_at=now())
                store.put('jobs', job_id, {k: v for k, v in job.items() if k != 'result'})
        except Exception as exc:
            with jobs_lock:
                job.update(status='failed', stage='Failed', error=f'Backend operation failed ({type(exc).__name__}). No success is claimed.', completed_at=now())
                try:
                    store.put('jobs', job_id, {k: v for k, v in job.items() if k != 'result'})
                except Exception:
                    pass
        finally:
            if kind == 'evolution':
                evolution_lock.release()

    pool.submit(worker)
    return {'job_id': job_id, 'status': 'pending'}


@app.get('/health')
def health():
    return {'status': 'ok', 'application': 'BayFlow', 'database': atlas.status(), 'model_available': bool(os.getenv('ANTHROPIC_API_KEY'))}


@app.get('/network')
def network():
    return get_network()


@app.get('/scenarios')
def scenarios():
    return SCENARIOS


@app.get('/database/status')
def database_status(offline: bool = False):
    return select_store(offline, required=False).status()


@app.post('/simulation/run', status_code=202)
def run_simulation(request: RunRequest):
    store = select_store(request.offline)
    config = current_config(store) if request.mode == 'evolving' else HarnessConfig()
    return submit(store, 'simulation', lambda progress: execute_run(store, config, request.seed, request.mode, request.scenario))


@app.get('/jobs/{job_id}')
def get_job(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, 'Job not available in this process; inspect persisted simulation/evaluation records for history.')
        return jobs[job_id]


@app.get('/simulation/{run_id}/frames')
def get_frames(run_id: str, offline: bool = False):
    store = select_store(offline)
    if not store.get('simulation_runs', run_id):
        raise HTTPException(404, 'Run not found')
    return sorted(store.list('simulation_frames', {'run_id': run_id}, limit=10000), key=lambda f: f['minute'])


@app.get('/simulation/{run_id}')
def get_run(run_id: str, offline: bool = False):
    store = select_store(offline)
    result = store.get('simulation_runs', run_id)
    if not result:
        raise HTTPException(404, 'Run not found')
    result['frames'] = sorted(store.list('simulation_frames', {'run_id': run_id}, limit=10000), key=lambda f: f['minute'])
    result['traces'] = store.list('agent_traces', {'run_id': run_id}, limit=10000)
    return result


@app.get('/harness/current')
def harness_current(offline: bool = False):
    store = select_store(offline, required=False)
    try:
        return current_config(store).model_dump()
    except RuntimeError:
        return dict(HarnessConfig().model_dump(), persistence='unavailable', persisted=False)


@app.get('/harness/versions')
def harness_versions(offline: bool = False):
    store = select_store(offline, required=False)
    try:
        active = current_config(store).version
        return [dict(v, active=v['version'] == active) for v in store.list('harness_versions', limit=10000)]
    except RuntimeError:
        return []


@app.get('/harness/evaluations')
def harness_evaluations(offline: bool = False):
    store = select_store(offline, required=False)
    try:
        return store.list('evaluation_results', limit=1000)
    except RuntimeError:
        return []


@app.post('/harness/evolve', status_code=202)
def harness_evolve(request: EvolveRequest):
    store = select_store(request.offline)
    if not evolution_lock.acquire(blocking=False):
        raise HTTPException(409, 'An evolution or rollback is already in progress.')
    return submit(store, 'evolution', lambda progress: evolve(store, request.seed, request.iterations, request.use_llm, progress))


@app.post('/harness/rollback')
def harness_rollback(request: RollbackRequest):
    store = select_store(request.offline)
    if not evolution_lock.acquire(blocking=False):
        raise HTTPException(409, 'An evolution is in progress.')
    try:
        version = store.get('harness_versions', request.version)
        if not version:
            raise HTTPException(404, 'Harness version not found')
        if version.get('accepted') is False:
            raise HTTPException(409, 'Cannot activate a rejected candidate.')
        config = HarnessConfig.model_validate(version['config'])
        previous = current_config(store)
        decision_id = str(uuid4())
        store.put('deployment_decisions', decision_id, {'kind': 'rollback', 'version': config.version, 'parent_version': previous.version, 'accepted': True, 'reason': 'Operator requested rollback to a previously accepted configuration.'})
        store.put('control', 'active_harness', {'version': config.version, 'decision_id': decision_id})
        return config.model_dump()
    finally:
        evolution_lock.release()
