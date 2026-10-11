"""Frozen reference, typed rule execution and passenger/resource accounting."""
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from backend.app.models import HarnessConfig
from backend.app.city_simulator import simulate_city, CITY_EVALUATOR


def hold_config(**changes):
    rule=dict(id='transfer_hold',description='Wait briefly for incoming transfer riders',signal='incoming_transfer_riders',threshold=1,scope_operators=['BART','Muni Metro'],action='hold_for_transfer',max_hold_minutes=3)
    rule.update(changes)
    return HarnessConfig(context_policy='transfer_neighbors',active_tools=['local_dispatch_optimizer','transfer_optimizer'],rules=[rule])


@pytest.fixture(scope='module')
def reference_run():
    return simulate_city(HarnessConfig(),seed=42)


def test_city_v1_metrics_exactly_match_before_policy_refactor(reference_run):
    expected=json.loads(Path(__file__).with_name('city_v1_seed42.json').read_text())
    assert reference_run['metrics']==expected
    assert reference_run['rule_telemetry']=={}
    assert reference_run['metrics']['active_services']==82


@pytest.mark.parametrize('patch',[
    {'active_tools':['local_dispatch_optimizer']},
    {'context_policy':'local_only'},
    {'policy':{'urgent_wait_minutes':16}},
])
def test_architecture_validates_rule_access_and_policy_bounds(patch):
    values=hold_config().model_dump();values.update(patch)
    with pytest.raises(ValidationError):HarnessConfig(**values)


def test_invalid_rule_ids_hold_bounds_and_executable_content():
    values=hold_config().model_dump();values['rules']*=2
    with pytest.raises(ValidationError):HarnessConfig(**values)
    with pytest.raises(ValidationError):hold_config(max_hold_minutes=6)
    with pytest.raises(ValidationError):hold_config(threshold=1001)
    with pytest.raises(ValidationError):hold_config(action='execute_python')


def test_hold_rules_execute_without_inventing_passengers_capacity_or_resources(reference_run):
    config=hold_config();with_rules=simulate_city(config,seed=42)
    without=config.model_dump();without['rules']=[]
    no_rules=simulate_city(HarnessConfig(**without),seed=42)
    tele=with_rules['rule_telemetry']['transfer_hold']
    assert tele['holds']>0 and tele['fired']>=tele['holds'] and tele['hold_minutes']>0
    assert with_rules['metrics']!=no_rules['metrics']
    assert with_rules['evaluator']==no_rules['evaluator']==CITY_EVALUATOR
    assert with_rules['metrics']['generated_passengers']==reference_run['metrics']['generated_passengers']
    for metric in ['capacity_violations','feasibility_violations']:assert with_rules['metrics'][metric]==0
    assert all(f['passenger_balance']['conserved'] for f in with_rules['frames'])
    assert all(g['generated']==sum(g[k] for k in ['waiting','walking','riding','arrived']) for f in with_rules['frames'] for g in f['passenger_flows'])
    assert all(v['occupancy']<=v['capacity'] for f in with_rules['frames'] for v in f['vehicles'])
    assert all(0<t['hold_minutes']<=3 for t in with_rules['traces'] if t['action']=='hold_for_transfer' and t['tool']!='operating_rule')
    # Original requested journeys, demand and compliance seeds remain untouched.
    intents=lambda r:{g['parent_intent']:(g['origin'],g['destination'],g['reference_arrival'],g['original_path']) for g in r['passenger_groups']}
    assert intents(with_rules)==intents(no_rules)
    assert sum(t['operator']=='BART' for t in with_rules['traces'] if t.get('tool')=='operating_rule')>0


def test_mutable_advisory_eta_limit_cannot_change_frozen_arrival_metric(reference_run):
    tuned=simulate_city(HarnessConfig(policy={'advisory_eta_slack_minutes':0}),seed=42)
    assert tuned['metrics']==reference_run['metrics']
    assert tuned['evaluator']==CITY_EVALUATOR
