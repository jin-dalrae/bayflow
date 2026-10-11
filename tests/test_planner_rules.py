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


def test_rejected_frequency_candidate_gets_distinct_replanning_hypothesis():
    current=HarnessConfig();failure=diagnose(run())
    # A rejected hold is not repeated; a rejected slow frequency test changes cadence.
    hold=rule_plan(current,failure).candidate
    first=rule_plan(current,failure,[{'accepted':False,'candidate':hold.model_dump()}]).candidate
    next_plan=rule_plan(current,failure,[{'accepted':False,'candidate':hold.model_dump()},{'accepted':False,'candidate':first.model_dump()}]).candidate
    assert first.model_dump()!=next_plan.model_dump()
    assert next_plan.replanning_interval_minutes==5


def test_fallback_does_not_repeat_a_third_rejected_cadence():
    current=HarnessConfig();failure=diagnose(run());history=[];candidates=[]
    for _ in range(4):
        candidate=rule_plan(current,failure,history).candidate
        behavior=candidate.model_dump(exclude={'version'})
        assert behavior not in candidates
        candidates.append(behavior);history.append({'accepted':False,'candidate':candidate.model_dump()})
