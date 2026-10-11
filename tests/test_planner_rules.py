"""Planner contract tests; mock provider responses, never claim live model calls."""
import json
from types import SimpleNamespace
from backend.app.models import HarnessConfig
from backend.app.planner import propose,diagnose,rule_plan


def run():
    return dict(config=HarnessConfig().model_dump(),scenario='city_commute',metrics={'boarding_within_10_minutes_rate':.5,'missed_transfers':10,'transfer_opportunities':100,'crowding_exposure_passenger_minutes':200},frames=[],traces=[dict(action='boarding_denied',tool='passenger_queue',edge_id='missing',operator='Muni Bus',count=7,transfer=True,wait_minutes=18)],rule_telemetry={'hold_test':{'holds':3}})


def test_diagnosis_includes_rules_policy_exact_denials_and_transfer_waits():
    failure=diagnose(run())
    assert failure['rule_telemetry']=={'hold_test':{'holds':3}}
    assert failure['current_policy']==HarnessConfig().policy.model_dump()
    assert failure['top_failure_edges'][0]['denied_boardings']==7
    assert failure['top_transfer_wait_edges'][0]['max_denied_wait_minutes']==18


def test_gemini_schema_failure_is_repaired_once_with_feedback(monkeypatch):
    from google import genai
    requests=[]
    valid=dict(candidate=HarnessConfig().model_dump(),diagnosis='Measured transfer failures need investigation.',rationale='Test a bounded configuration using measured failure evidence.',expected_improvement='A falsifiable transfer hypothesis.',confidence=.5)
    class Client:
        def __init__(self,**kwargs):self.models=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def generate_content(self,**kwargs):
            requests.append(kwargs)
            text='{"invalid":true}' if len(requests)==1 else json.dumps(valid)
            return SimpleNamespace(text=text,usage_metadata=None,model_version='test-provider-response')
    monkeypatch.setenv('LLM_PROVIDER','gemini');monkeypatch.setenv('GEMINI_API_KEY','test-key-not-a-secret')
    monkeypatch.setattr(genai,'Client',Client)
    proposal,meta=propose(HarnessConfig(),run(),use_llm=True)
    assert meta['kind']=='llm' and meta['attempts']==2 and len(meta['validation_errors'])==1
    assert requests[0]['config'].max_output_tokens==16384
    assert 'validation_feedback' in json.loads(requests[1]['contents'])
    assert proposal.candidate==HarnessConfig()


def test_fallback_tests_one_untried_hypothesis_at_a_time():
    from backend.app.planner import changed_fields, MAX_CHANGED_FIELDS
    current=HarnessConfig();failure=diagnose(run());history=[];seen=[]
    for _ in range(8):
        candidate=rule_plan(current,failure,history).candidate
        behavior=candidate.model_dump(exclude={'version'})
        assert behavior not in seen
        assert 1<=len(changed_fields(current,candidate))<=MAX_CHANGED_FIELDS
        seen.append(behavior);history.append({'accepted':False,'candidate':candidate.model_dump()})


def test_first_fallback_changes_a_single_policy_knob():
    from backend.app.planner import changed_fields
    candidate=rule_plan(HarnessConfig(),diagnose(run())).candidate
    assert changed_fields(HarnessConfig(),candidate)==['policy.dispatch_threshold_local']


def test_bundled_llm_candidate_is_rejected_then_fallback_is_labeled(monkeypatch):
    from google import genai
    bundle=HarnessConfig(coordination_mode='regional',context_policy='regional_shared',replanning_interval_minutes=5,
        active_agents=['muni_agent','bart_agent','caltrain_agent','regional_coordinator'],
        active_tools=['local_dispatch_optimizer','regional_coordination','service_frequency_optimizer']).model_dump()
    reply=dict(candidate=bundle,diagnosis='Measured failures suggest regional coordination.',rationale='Enable several coordination features together.',expected_improvement='Better service.',confidence=.5)
    class Client:
        def __init__(self,**kwargs):self.models=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def generate_content(self,**kwargs):return SimpleNamespace(text=json.dumps(reply),usage_metadata=None,model_version='test')
    monkeypatch.setenv('LLM_PROVIDER','gemini');monkeypatch.setenv('GEMINI_API_KEY','test-key-not-a-secret')
    monkeypatch.setattr(genai,'Client',Client)
    proposal,meta=propose(HarnessConfig(),run(),use_llm=True)
    assert meta['kind']=='rule_based' and meta['attempts']==2
    assert 'at most 3 changed fields' in meta['validation_errors'][0]['message']
