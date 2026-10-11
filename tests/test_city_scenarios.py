"""Immutable artificial experiments change the world, never the evaluation objective."""

from dataclasses import FrozenInstanceError
from collections import defaultdict
import pytest
from backend.app.city_scenarios import (
    CITY_SCENARIOS,
    get_city_scenario,
    get_city_profiles,
)
from backend.app.city_network import get_city_network
from backend.app.models import HarnessConfig
from backend.app.simulator import simulate


@pytest.fixture(scope="module")
def profiles():
    return {
        name: simulate(
            HarnessConfig(),
            seed=42,
            mode="static",
            scenario="city_commute",
            city_profile=name,
        )
        for name in CITY_SCENARIOS
    }


def intent_snapshot(run):
    groups = {}
    counts = defaultdict(int)
    for group in run["passenger_groups"]:
        identity = group["parent_intent"]
        counts[identity] += group["count"]
        fields = (
            group["born"],
            group["origin"],
            group["destination"],
            group["reference_arrival"],
            tuple(group["original_path"]),
        )
        assert identity not in groups or groups[identity] == fields
        groups[identity] = fields
    return {identity: (counts[identity], fields) for identity, fields in groups.items()}


def test_registry_immutable_and_unknown_profile_rejected():
    assert len(get_city_profiles()) == 6
    with pytest.raises(TypeError):
        CITY_SCENARIOS["invented"] = get_city_scenario()
    with pytest.raises(FrozenInstanceError):
        get_city_scenario("stadium_exit").stadium_multiplier = 99
    with pytest.raises(ValueError):
        simulate(scenario="city_commute", city_profile="invented")


@pytest.mark.parametrize("profile", list(CITY_SCENARIOS))
def test_scenario_conserves_people_capacity_and_objective(profiles, profile):
    run = profiles[profile]
    assert run["accounting"]["conserved"]
    assert all(frame["passenger_balance"]["conserved"] for frame in run["frames"])
    assert all(
        v["occupancy"] <= v["capacity"]
        for frame in run["frames"]
        for v in frame["vehicles"]
    )
    assert run["evaluator"] == profiles["standard"]["evaluator"]
    assert run["resource_constraints"] == profiles["standard"]["resource_constraints"]
    assert run["metrics"]["feasibility_violations"] == 0
    assert run["metrics"]["capacity_violations"] == 0


def test_disruptions_change_actual_timing_and_availability(profiles):
    edges = {edge["id"]: edge for edge in get_city_network()["edges"]}
    gap = profiles["bus_driver_shortage"]
    route38_departures = []
    for frame in gap["frames"]:
        if not 30 <= frame["minute"] < 150:
            continue
        for vehicle in frame["vehicles"]:
            edge = edges[vehicle["edge_id"]]
            if (
                edge["operator"] == "Muni Bus"
                and edge["service"] == "38"
                and vehicle["progress"] == 0
            ):
                route38_departures.append(vehicle)
                assert (
                    (frame["minute"] - edge["departure_offset_minutes"])
                    // edge["headway_minutes"]
                ) % 2 == 0
    assert route38_departures
    assert (
        gap["metrics"]["total_passenger_delay_minutes"]
        > profiles["standard"]["metrics"]["total_passenger_delay_minutes"]
    )
    interruption = profiles["bart_interruption"]
    selected = [
        event
        for frame in interruption["frames"]
        for event in frame["passenger_events"]
        if event["action"] == "boarded"
        and event["operator"] == "BART"
        and event["node"] in {"BART:EMBR", "BART:MONT", "BART:POWL"}
        and 30 <= event["minute"] < 120
    ]
    assert selected
    assert all(
        event["arrival_minute"] - event["minute"]
        == edges[event["edge_id"]]["travel_minutes"] + 8
        for event in selected
    )
    assert (
        interruption["metrics"]["total_passenger_delay_minutes"]
        > profiles["standard"]["metrics"]["total_passenger_delay_minutes"]
    )
    assert any(
        event["type"] == "delay"
        for frame in interruption["frames"]
        for event in frame["events"]
    )


def test_surge_demand_compliance_and_balanced_control_are_explicit(profiles):
    standard = profiles["standard"]
    surge = profiles["stadium_exit"]
    control = profiles["balanced_control"]
    low = profiles["low_compliance"]
    assert (
        surge["metrics"]["generated_passengers"]
        > standard["metrics"]["generated_passengers"]
    )
    original = intent_snapshot(standard)
    crowd = intent_snapshot(surge)
    assert set(original) == set(crowd)
    assert any(crowd[key][0] == original[key][0] * 3 for key in original)
    assert all(crowd[key][1] == original[key][1] for key in original)
    assert low["scenario_parameters"]["advisory_acceptance_rate"] == 0.10
    assert intent_snapshot(low) == original
    assert (
        control["metrics"]["generated_passengers"]
        < standard["metrics"]["generated_passengers"]
    )
    assert not any(frame["events"] for frame in control["frames"])
    assert not control["city_profile"]["standard_disruptions"]


@pytest.mark.parametrize(
    "profile",
    [
        "bus_driver_shortage",
        "bart_interruption",
        "stadium_exit",
        "low_compliance",
        "balanced_control",
    ],
)
def test_demand_and_requested_eta_frozen_across_harnesses(profiles, profile):
    configured = HarnessConfig(
        replanning_interval_minutes=5,
        coordination_mode="regional",
        context_policy="regional_shared",
        active_agents=[
            "muni_agent",
            "bart_agent",
            "caltrain_agent",
            "regional_coordinator",
        ],
        active_tools=[
            "local_dispatch_optimizer",
            "regional_coordination",
            "transfer_optimizer",
            "passenger_advisory",
        ],
        optimization_strategy="transfer_aware",
        verification_policy="strict",
    )
    variant = simulate(
        configured,
        seed=42,
        mode="evolving",
        scenario="city_commute",
        city_profile=profile,
    )
    assert intent_snapshot(variant) == intent_snapshot(profiles[profile])
    assert variant["scenario_parameters"] == profiles[profile]["scenario_parameters"]
    assert variant["evaluator"] == profiles[profile]["evaluator"]
    assert variant["resource_constraints"] == profiles[profile]["resource_constraints"]
    assert variant["accounting"]["conserved"]
