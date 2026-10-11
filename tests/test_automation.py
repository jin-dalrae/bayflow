"""Backend monitoring rather than a frontend timer or forced mutation."""
import pytest
from backend.app.automation import detect_failure,operate
from backend.app.city_simulator import simulate_city
from backend.app.models import HarnessConfig
from backend.app.evolution import current_config
from backend.app.store import Store


def test_monitor_detects_matured_failure_in_real_run():
    run=simulate_city(HarnessConfig());run.update(run_id='observed-test',harness_version='v1')
    trigger=detect_failure(run)
    assert trigger['source']=='backend_failure_monitor' and trigger['minute']>=45
    assert all(o['matured_intents']>=200 for o in trigger['observations'])
    assert trigger['source_run_id']=='observed-test'


def test_healthy_boarding_run_does_not_call_planner(monkeypatch):
    from backend.app import automation
    healthy=dict(run_id='healthy-test',harness_version='v1',persistence='offline_preview',passenger_groups=[dict(cohort_id='all',count=300,born=20)],frames=[dict(minute=30,passenger_events=[dict(cohort_id='all',action='boarded',first_boarding=True,count=300,minute=25)],passenger_service={}),dict(minute=45,passenger_events=[],passenger_service={})])
    monkeypatch.setattr(automation,'execute_run',lambda *a,**k:healthy)
    def fail(*a,**k):raise AssertionError('Healthy run must not request a mutation')
    monkeypatch.setattr(automation,'evolve',fail)
    store=Store(offline=True);result=operate(store,use_llm=False)
    assert result['automatic_trigger'] is None and result['decisions']==[]
    assert store.list('automation_events')[0]['status']=='healthy'


def test_scenario_champions_do_not_inherit_other_scenario_selection():
    store=Store(offline=True);current_config(store)
    c=HarnessConfig(version='v2')
    store.put('harness_versions','v2',dict(version='v2',config=c.model_dump(),accepted=True,scenario='event_surge'))
    store.put('control','active_harness',{'version':'v2'})
    assert current_config(store,scenario='city_commute').version=='v1'
    assert current_config(store,scenario='event_surge').version=='v2'
