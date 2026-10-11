import pytest
from pydantic import ValidationError
from backend.app.models import HarnessConfig
from backend.app.simulator import simulate, EVALUATOR
from backend.app.network import get_network

def test_seed_determinism_and_conservation():
    a=simulate(seed=42); b=simulate(seed=42)
    assert a['metrics']==b['metrics']
    assert a['frames']==b['frames']
    assert a['accounting']['conserved']
    assert a['accounting']['generated']==sum(a['accounting'][k] for k in ['served','queued','onboard'])

def test_capacity_and_disruptions():
    r=simulate(mode='static')
    assert all(v['occupancy']<=v['capacity'] for f in r['frames'] for v in f['vehicles'])
    driver_frames=[f for f in r['frames'] if 80<=f['minute']<170 and f['minute']%30==15]
    assert all(not any(v['operator']=='Muni Bus' and v['progress']==0 for v in f['vehicles']) for f in driver_frames)
    delay_frames=[f for f in r['frames'] if 130<=f['minute']<190 and f['minute']%30==15]
    assert all(not any(v['operator']=='BART' and v['progress']==0 for v in f['vehicles']) for f in delay_frames)
    assert r['metrics']['missed_transfers']>0
    assert any(e['type']=='surge' for f in r['frames'] for e in f['events'])

def test_mutation_changes_executable_behavior():
    a=simulate(HarnessConfig())
    config=HarnessConfig(active_tools=['local_dispatch_optimizer','transfer_optimizer'],optimization_strategy='transfer_aware')
    b=simulate(config)
    assert a['metrics']!=b['metrics']
    assert a['frames']!=b['frames']
    assert a['evaluator']==b['evaluator']==EVALUATOR
    assert b['accounting']['conserved']

def test_strict_schema():
    for change in [{'active_tools':['exec_python']},{'planning_horizon_minutes':1000},{'objective_weights':{}},{'coordination_mode':'regional'}]:
        with pytest.raises(ValidationError): HarnessConfig(**change)

def test_all_operators_and_reference_delay():
    operators={e['operator'] for e in get_network()['edges']}
    assert {'Muni Bus','Muni Metro','Caltrain','BART','walk'} <= operators
    r=simulate(mode='static',scenario='commuter')
    assert r['metrics']['additional_operating_cost']==0
    assert r['metrics']['total_passenger_delay_minutes']>=0
    assert 'undisrupted' in r['evaluator']['reference']

@pytest.mark.parametrize('scenario',['event_surge','commuter','accident'])
def test_every_frame_conserves_passengers_and_safety(scenario):
    config=HarnessConfig(coordination_mode='regional',active_agents=['muni_agent','bart_agent','caltrain_agent','regional_coordinator','demand_forecaster'],active_tools=['local_dispatch_optimizer','regional_coordination','transfer_optimizer','demand_forecast','feasibility_checker'],context_policy='regional_shared',optimization_strategy='regional_predictive',replanning_interval_minutes=5,verification_policy='strict')
    r=simulate(config,seed=101,scenario=scenario)
    for frame in r['frames']:
        assert frame['generated']==frame['served']+sum(frame['queues'].values())+sum(v['occupancy'] for v in frame['vehicles'])
    assert r['metrics']['capacity_violations']==0
    assert r['metrics']['feasibility_violations']==0
    nominal={edge['id']:edge['capacity'] for edge in get_network()['edges']}
    assert all(v['capacity']==nominal[v['edge_id']] for frame in r['frames'] for v in frame['vehicles'])

def test_delay_persists_vehicle_into_next_interval():
    r=simulate(mode='static')
    delayed=[v for f in r['frames'] if f['minute']==155 for v in f['vehicles'] if v['operator']=='BART' and v['id'].startswith('150-')]
    assert delayed
    assert any(v['progress']==0.5 for v in delayed)
    assert all(0<v['progress']<1 for v in delayed)

def test_standby_resource_changes_cost_and_verification_trace():
    basic=simulate(HarnessConfig())
    strict=simulate(HarnessConfig(verification_policy='strict',active_tools=['local_dispatch_optimizer','feasibility_checker']))
    assert basic['metrics']['extra_departures']>0
    assert basic['metrics']['additional_operating_cost']>0
    assert strict['traces'] and all(t['verification']=='strict resource and horizon check' for t in strict['traces'])

def test_regional_policy_preserves_standby_in_low_load():
    """Sharing context alone must not justify spending on nearly empty departures."""
    config=HarnessConfig(coordination_mode='regional',active_agents=['muni_agent','bart_agent','caltrain_agent','regional_coordinator','demand_forecaster'],active_tools=['local_dispatch_optimizer','regional_coordination','transfer_optimizer','demand_forecast','feasibility_checker'],context_policy='regional_shared',optimization_strategy='regional_predictive',planning_horizon_minutes=90,replanning_interval_minutes=5,memory_window_steps=18,verification_policy='strict')
    for seed in [42,101]:
        fixed=simulate(HarnessConfig(),seed=seed,scenario='commuter')
        regional=simulate(config,seed=seed,scenario='commuter')
        assert regional['metrics']['additional_operating_cost']<=fixed['metrics']['additional_operating_cost']
        assert regional['metrics']['objective']<=fixed['metrics']['objective']*1.05
    surge=simulate(config,seed=101)
    assert surge['metrics']['extra_departures']>0
    assert any(t['regional_overload'] for t in surge['traces'])
