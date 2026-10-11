"""Explicit real Gemini/organizer-Atlas city-rule acceptance artifact."""
import json
from pathlib import Path
import pytest
from backend.app.store import Store
from backend.app.main import seed_store
from backend.app.evolution import evolve,current_config

@pytest.mark.atlas
@pytest.mark.llm
def test_city_rules_real_gemini_atlas(request):
    if not (request.config.getoption('--atlas') and request.config.getoption('--llm')):
        pytest.skip('Explicit --atlas --llm required for real persistence/model tokens')
    store=Store();store.ensure();seed_store(store)
    existing=current_config(store)
    assert existing.policy and isinstance(existing.rules,list)
    result=evolve(store,seed=42,iterations=3,use_llm=True,scenario='city_commute',progress=lambda stage:print(stage,flush=True))
    artifact={k:v for k,v in result.items() if k!='replay'}
    artifact['database_verification']=store.status()
    artifact['persisted_rule_telemetry']=[]
    for decision in result['decisions']:
        mid=decision['mutation_id']
        saved=store.get('evaluation_results',mid)
        assert saved['accepted']==store.get('deployment_decisions',mid)['accepted']==decision['accepted']
        assert len(saved['evaluation_seeds'])==5 and len(saved['per_seed'])==5
        assert saved['config_diff']==decision['config_diff']
        if saved['accepted']:assert saved['seed_wins']>=3
        run=store.get('simulation_runs',decision['development_run_id'])
        artifact['persisted_rule_telemetry'].append(dict(run_id=run['run_id'],rule_telemetry=run.get('rule_telemetry',{})))
    for run_id in result['run_ids'].values():
        run=store.get('simulation_runs',run_id)
        frames=store.list('simulation_frames',{'run_id':run_id},limit=10000)
        assert run['status']=='completed' and len(frames)==run['frame_count']
        assert all(f['passenger_balance']['conserved'] for f in frames)
        assert run['metrics']['capacity_violations']==run['metrics']['feasibility_violations']==0
    Path('demo/evaluation-city-rules-atlas.json').write_text(json.dumps(artifact,indent=2))
    assert artifact['database_verification']['verified_read_write']
    assert any(d['planner']['kind']=='llm' for d in result['decisions']), 'Artifact saved; model failed and fallbacks were used'
