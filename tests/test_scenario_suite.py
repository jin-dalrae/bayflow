"""Suite evidence must not confuse measured rejection with performance success."""
from scripts.scenario_suite import summarize_case


def decision(version, accepted=False, age=.2):
    return dict(candidate=dict(version=version, policy=dict(age_weight=age)),
                accepted=accepted, config_diff=[dict(path="policy.age_weight")],
                planner=dict(kind="rule_based"), candidate_rule_telemetry={
                    "hold": dict(evaluations=8, fired=3, holds=2, hold_minutes=4, riders_affected=10)})


def test_rejected_feedback_is_not_reported_as_performance_gain():
    result = dict(automatic_trigger=dict(minute=45), decisions=[decision("v2"), decision("v3", age=.3)],
                  comparison=dict(fixed=dict(objective=.5), evolved=dict(objective=.5)))
    evidence = summarize_case(result, [dict(lesson="hold worsened objective")])
    assert evidence["distinct_policy_hypotheses"] == 2
    assert evidence["later_hypothesis_after_recorded_outcome"]
    assert evidence["rejected"] == 2 and evidence["accepted"] == 0
    assert not evidence["qualifying_promotion"]
    assert evidence["development_replay_improvement_percent"] == 0
    assert evidence["rule_telemetry"]["holds"] == 4


def test_versions_do_not_make_repeated_hypotheses_distinct():
    evidence = summarize_case(dict(decisions=[decision("v2"), decision("v3")]), [])
    assert evidence["distinct_policy_hypotheses"] == 1
    assert not evidence["later_hypothesis_after_recorded_outcome"]
    assert evidence["development_replay_improvement_percent"] is None


def test_healthy_monitor_does_not_claim_evolution_or_learning():
    evidence = summarize_case(dict(automatic_trigger=None, decisions=[]), [])
    assert not evidence["automatic_failure_detected"]
    assert evidence["proposals"] == evidence["distinct_policy_hypotheses"] == 0
    assert not evidence["architecture_changed_in_candidates"]
    assert not evidence["qualifying_promotion"]
