import pytest
from pydantic import ValidationError
from backend.app.models import HarnessConfig
from backend.app.simulator import simulate, EVALUATOR
from backend.app.network import get_network


def test_seed_determinism_and_conservation():
    a = simulate(seed=42)
    b = simulate(seed=42)
    assert a["metrics"] == b["metrics"]
    assert a["frames"] == b["frames"]
    assert a["accounting"]["conserved"]
    assert a["accounting"]["generated"] == sum(
        a["accounting"][k] for k in ["served", "queued", "onboard"]
    )


def test_capacity_and_disruptions():
    r = simulate(mode="static")
    assert all(
        v["occupancy"] <= v["capacity"] for f in r["frames"] for v in f["vehicles"]
    )
    driver_frames = [
        f for f in r["frames"] if 80 <= f["minute"] < 170 and f["minute"] % 30 == 15
    ]
    assert all(
        not any(
            v["operator"] == "Muni Bus" and v["progress"] == 0 for v in f["vehicles"]
        )
        for f in driver_frames
    )
    delay_frames = [
        f for f in r["frames"] if 130 <= f["minute"] < 190 and f["minute"] % 30 == 15
    ]
    assert all(
        not any(v["operator"] == "BART" and v["progress"] == 0 for v in f["vehicles"])
        for f in delay_frames
    )
    assert r["metrics"]["missed_transfers"] > 0
    assert any(e["type"] == "surge" for f in r["frames"] for e in f["events"])


def test_mutation_changes_executable_behavior():
    a = simulate(HarnessConfig())
    config = HarnessConfig(
        active_tools=["local_dispatch_optimizer", "transfer_optimizer"],
        optimization_strategy="transfer_aware",
    )
    b = simulate(config)
    assert a["metrics"] != b["metrics"]
    assert a["frames"] != b["frames"]
    assert a["evaluator"] == b["evaluator"] == EVALUATOR
    assert b["accounting"]["conserved"]


def test_strict_schema():
    for change in [
        {"active_tools": ["exec_python"]},
        {"planning_horizon_minutes": 1000},
        {"objective_weights": {}},
        {"coordination_mode": "regional"},
    ]:
        with pytest.raises(ValidationError):
            HarnessConfig(**change)


def test_all_operators_and_reference_delay():
    operators = {e["operator"] for e in get_network()["edges"]}
    assert {"Muni Bus", "Muni Metro", "Caltrain", "BART", "walk"} <= operators
    r = simulate(mode="static", scenario="commuter")
    assert r["metrics"]["additional_operating_cost"] == 0
    assert r["metrics"]["total_passenger_delay_minutes"] >= 0
    assert "undisrupted" in r["evaluator"]["reference"]


@pytest.mark.parametrize("scenario", ["event_surge", "commuter", "accident"])
def test_every_frame_conserves_passengers_and_safety(scenario):
    config = HarnessConfig(
        coordination_mode="regional",
        active_agents=[
            "muni_agent",
            "bart_agent",
            "caltrain_agent",
            "regional_coordinator",
            "demand_forecaster",
        ],
        active_tools=[
            "local_dispatch_optimizer",
            "regional_coordination",
            "transfer_optimizer",
            "demand_forecast",
            "feasibility_checker",
        ],
        context_policy="regional_shared",
        optimization_strategy="regional_predictive",
        replanning_interval_minutes=5,
        verification_policy="strict",
    )
    r = simulate(config, seed=101, scenario=scenario)
    for frame in r["frames"]:
        assert frame["generated"] == frame["served"] + sum(
            frame["queues"].values()
        ) + sum(v["occupancy"] for v in frame["vehicles"])
    assert r["metrics"]["capacity_violations"] == 0
    assert r["metrics"]["feasibility_violations"] == 0
    nominal = {edge["id"]: edge["capacity"] for edge in get_network()["edges"]}
    assert all(
        v["capacity"] == nominal[v["edge_id"]]
        for frame in r["frames"]
        for v in frame["vehicles"]
    )


def test_delay_persists_vehicle_into_next_interval():
    r = simulate(mode="static")
    delayed = [
        v
        for f in r["frames"]
        if f["minute"] == 155
        for v in f["vehicles"]
        if v["operator"] == "BART" and v["id"].startswith("150-")
    ]
    assert delayed
    assert any(v["progress"] == 0.5 for v in delayed)
    assert all(0 < v["progress"] < 1 for v in delayed)


def test_standby_resource_changes_cost_and_verification_trace():
    basic = simulate(HarnessConfig())
    strict = simulate(
        HarnessConfig(
            verification_policy="strict",
            active_tools=["local_dispatch_optimizer", "feasibility_checker"],
        )
    )
    assert basic["metrics"]["extra_departures"] > 0
    assert basic["metrics"]["additional_operating_cost"] > 0
    assert strict["traces"] and all(
        t["verification"] == "strict resource and horizon check"
        for t in strict["traces"]
        if t["action"] == "standby_dispatch"
    )


def test_regional_policy_preserves_standby_in_low_load():
    """Sharing context alone must not justify spending on nearly empty departures."""
    config = HarnessConfig(
        coordination_mode="regional",
        active_agents=[
            "muni_agent",
            "bart_agent",
            "caltrain_agent",
            "regional_coordinator",
            "demand_forecaster",
        ],
        active_tools=[
            "local_dispatch_optimizer",
            "regional_coordination",
            "transfer_optimizer",
            "demand_forecast",
            "feasibility_checker",
        ],
        context_policy="regional_shared",
        optimization_strategy="regional_predictive",
        planning_horizon_minutes=90,
        replanning_interval_minutes=5,
        memory_window_steps=18,
        verification_policy="strict",
    )
    for seed in [42, 101]:
        fixed = simulate(HarnessConfig(), seed=seed, scenario="commuter")
        regional = simulate(config, seed=seed, scenario="commuter")
        assert (
            regional["metrics"]["additional_operating_cost"]
            <= fixed["metrics"]["additional_operating_cost"]
        )
        assert regional["metrics"]["objective"] <= fixed["metrics"]["objective"] * 1.05
    surge = simulate(config, seed=101)
    assert surge["metrics"]["extra_departures"] > 0
    assert any(t.get("regional_overload", False) for t in surge["traces"])


def test_operator_controllers_observe_only_authorized_context_and_agents():
    config = HarnessConfig(active_agents=["muni_agent", "bart_agent"])
    result = simulate(config)
    observations = [trace for trace in result["traces"] if trace["action"] == "observe"]
    assert {trace["agent"] for trace in observations} == {"muni_agent", "bart_agent"}
    edges = {edge["id"]: edge for edge in get_network()["edges"]}
    for trace in observations:
        expected = (
            {"Muni Bus", "Muni Metro"} if trace["agent"] == "muni_agent" else {"BART"}
        )
        assert all(
            edges[eid]["operator"] in expected for eid in trace["observed_queues"]
        )
        assert trace["minute"] % config.replanning_interval_minutes == 0
        assert trace["retained_observations"] <= config.memory_window_steps
    shared_config = HarnessConfig(context_policy="regional_shared")
    shared = simulate(shared_config)
    shared_observation = next(
        trace for trace in shared["traces"] if trace["action"] == "observe"
    )
    assert {
        edges[eid]["operator"] for eid in shared_observation["observed_queues"]
    } == {"Muni Bus", "Muni Metro", "BART", "Caltrain"}


def test_each_operator_executes_real_priority_tool_when_enabled():
    config = HarnessConfig(
        active_tools=["local_dispatch_optimizer", "transfer_optimizer"],
        optimization_strategy="transfer_aware",
    )
    result = simulate(config)
    tools = [
        trace for trace in result["traces"] if trace["action"] == "boarding_priority"
    ]
    assert {trace["agent"] for trace in tools} == {
        "muni_agent",
        "bart_agent",
        "caltrain_agent",
    }
    edges = {edge["id"]: edge for edge in get_network()["edges"]}
    for trace in tools:
        assert trace["tool"] == "transfer_optimizer"
        assert trace["observed_queue"] > 0
        assert trace["available_capacity"] >= edges[trace["edge_id"]]["capacity"]
        assert trace["operator"] == edges[trace["edge_id"]]["operator"]
    assert not simulate(mode="static")["traces"]


def test_passenger_ledger_conserves_people_in_every_frame_and_demand_pair():
    run = simulate(seed=42)
    for frame in run['frames']:
        balance = frame['passenger_balance']
        assert balance['conserved']
        assert balance['generated'] == sum(balance[k] for k in ('waiting', 'walking', 'riding', 'arrived'))
        for flow in frame['passenger_flows']:
            assert flow['generated'] == sum(flow[k] for k in ('waiting', 'walking', 'riding', 'arrived'))
            assert all(flow[k] >= 0 for k in ('waiting', 'walking', 'riding', 'arrived'))
        assert sum(f['generated'] for f in frame['passenger_flows']) == balance['generated']
    assert run['frames'][-1]['passenger_balance']['arrived'] == run['metrics']['served_passengers']
    # Adding observability must not change the measured baseline.
    assert run['metrics']['objective'] == 0.305224


def test_journey_events_prove_boarding_before_arrival_without_teleporting():
    from collections import defaultdict
    departures, alighted, arrived = defaultdict(int), defaultdict(int), defaultdict(int)
    groups = {g['cohort_id']: g for g in simulate(seed=42)['passenger_groups']}
    run = simulate(seed=42)
    for frame in run['frames']:
        for event in frame['passenger_events']:
            group = groups[event['cohort_id']]
            assert event['origin'] == group['origin'] and event['destination'] == group['destination']
            assert event['minute'] >= group['born']
            if event['action'] in ('boarded', 'walking'):
                departures[(event['cohort_id'], event['vehicle_id'])] += event['count']
            elif event['action'] == 'leg_arrival':
                key = (event['cohort_id'], event['vehicle_id'])
                alighted[key] += event['count']
                assert alighted[key] <= departures[key]
            elif event['action'] == 'arrived':
                assert event['node'] == group['destination']
                arrived[event['cohort_id']] += event['count']
                assert arrived[event['cohort_id']] <= group['count']
    assert sum(arrived.values()) == run['metrics']['served_passengers']
    event_group = next(g for g in groups.values() if g['origin'] == 'chase')
    assert arrived[event_group['cohort_id']] == event_group['count'] == 95
