import time
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def complete(job_id):
    for _ in range(100):
        job = client.get(f'/jobs/{job_id}').json()
        if job['status'] in ('completed', 'failed'):
            assert job['status'] == 'completed', job
            return job
        time.sleep(.01)
    raise AssertionError('Job did not complete')


def test_network_and_real_backend_generated_run():
    network = client.get('/network').json()
    assert 15 <= len(network['nodes']) <= 30
    response = client.post('/simulation/run', json={'mode': 'fixed', 'seed': 42, 'scenario': 'event_surge', 'offline': True})
    assert response.status_code == 202
    job = complete(response.json()['job_id'])
    result = job['result']
    assert result['accounting']['conserved']
    persisted = client.get(f'/simulation/{result["run_id"]}?offline=true').json()
    assert persisted['metrics'] == result['metrics']
    assert len(persisted['frames']) == 85
    assert client.get('/database/status?offline=true').json()['eligible'] is False


def test_evolution_progress_history_and_rollback():
    response = client.post('/harness/evolve', json={'offline': True, 'use_llm': False, 'iterations': 2, 'seed': 42})
    assert response.status_code == 202
    job = complete(response.json()['job_id'])
    assert len(job['history']) >= 12
    assert job['result']['current']['version'] == 'v3'
    assert client.get('/harness/current?offline=true').json()['version'] == 'v3'
    assert client.post('/harness/rollback', json={'offline': True, 'version': 'v2'}).status_code == 409
    rollback = client.post('/harness/rollback', json={'offline': True, 'version': 'v1'})
    assert rollback.status_code == 200
    assert client.get('/harness/current?offline=true').json()['version'] == 'v1'


def test_invalid_api_inputs_and_missing_run():
    assert client.post('/simulation/run', json={'offline': True, 'mode': 'fake'}).status_code == 422
    assert client.post('/harness/evolve', json={'offline': True, 'iterations': 99}).status_code == 422
    assert client.get('/simulation/missing?offline=true').status_code == 404
