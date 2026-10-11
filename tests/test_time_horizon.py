"""Extended synthetic demand and clock wrapping preserve the original experiment."""

import json
from pathlib import Path
import pytest
from backend.app.city_network import get_city_network
from backend.app.models import HarnessConfig
from backend.app.simulator import simulate


@pytest.fixture(scope="module")
def extended():
    return simulate(
        HarnessConfig(), seed=42, scenario="city_commute", horizon_minutes=720
    )


def test_extended_horizon_generates_more_riders_and_wraps_clock(extended):
    original = json.loads(Path(__file__).with_name("city_v1_seed42.json").read_text())
    assert (
        extended["metrics"]["generated_passengers"] > original["generated_passengers"]
    )
    assert extended["horizon_minutes"] == 720
    assert extended["scenario_parameters"]["horizon_minutes"] == 720
    assert len(extended["frames"]) == 721
    assert extended["frames"][-1]["minute"] == 720
    assert extended["frames"][-1]["time"] == "04:00"
    assert extended["frames"][-1]["day_offset"] == 1
    midnight = extended["frames"][480]
    assert midnight["time"] == "00:00" and midnight["day_offset"] == 1
    assert extended["synthetic_demand_schedule"]["observed"] is False


def test_extended_every_minute_conserves_and_preserves_physical_events(extended):
    for frame in extended["frames"]:
        assert frame["passenger_balance"]["conserved"]
        assert frame["generated"] == sum(
            frame["passenger_balance"][key]
            for key in ["arrived", "waiting", "walking", "riding"]
        )
        assert all(
            vehicle["occupancy"] <= vehicle["capacity"] for vehicle in frame["vehicles"]
        )
    assert extended["accounting"]["conserved"]
    assert any(
        event["action"] == "generated"
        for frame in extended["frames"]
        if frame["minute"] > 180
        for event in frame["passenger_events"]
    )
    assert any(
        event["action"] == "arrived"
        for frame in extended["frames"]
        if frame["minute"] > 180
        for event in frame["passenger_events"]
    )


def test_requested_initial_intents_unchanged_and_horizon_frozen_across_harnesses(
    extended,
):
    original = simulate(HarnessConfig(), seed=42, scenario="city_commute")

    def intents(run, cutoff):
        return {
            group["parent_intent"]: (
                group["born"],
                group["count"],
                group["origin"],
                group["destination"],
                group["reference_arrival"],
                group["original_path"],
            )
            for group in run["passenger_groups"]
            if group["born"] <= cutoff
        }

    assert intents(original, 120) == intents(extended, 120)
    alternative = simulate(
        HarnessConfig(replanning_interval_minutes=5),
        seed=42,
        scenario="city_commute",
        horizon_minutes=720,
    )
    assert intents(extended, 720) == intents(alternative, 720)
    assert extended["evaluator"] == alternative["evaluator"] == original["evaluator"]
    assert extended["scenario_parameters"] == alternative["scenario_parameters"]


@pytest.mark.parametrize("invalid", [179, 1441, True, 720.5, "720"])
def test_horizon_validation(invalid):
    with pytest.raises(ValueError):
        simulate(HarnessConfig(), scenario="city_commute", horizon_minutes=invalid)
    with pytest.raises(ValueError):
        get_city_network(horizon_minutes=invalid)


def test_topology_duration_metadata_and_original_event_unchanged():
    shorter = get_city_network(180)
    longer = get_city_network(1440)
    assert shorter["nodes"] is longer["nodes"] and shorter["edges"] is longer["edges"]
    assert longer["end_minute"] == 1440 and longer["horizon_minutes"] == 1440
    assert (
        simulate(seed=42)["metrics"]
        == simulate(seed=42, horizon_minutes=720)["metrics"]
    )


def test_extended_run_actually_boards_all_four_operators(extended):
    boarded = [
        event
        for frame in extended["frames"]
        for event in frame["passenger_events"]
        if event["action"] == "boarded"
    ]
    assert {event["operator"] for event in boarded} >= {
        "Muni Bus",
        "Muni Metro",
        "BART",
        "Caltrain",
    }
    assert extended["metrics"]["active_services"] == 83
    caltrain_groups = [
        group
        for group in extended["passenger_groups"]
        if group["requested_operator"] == "Caltrain"
        and group["origin"] in {"sf_caltrain", "millbrae_caltrain"}
    ]
    # The three frozen corridor intents; citywide commuters may also choose Caltrain.
    assert len(caltrain_groups) == 3
    assert {group["born"] for group in caltrain_groups} == {125, 155, 185}
    assert all(10 <= group["count"] <= 30 for group in caltrain_groups)
    edges = {edge["id"]: edge for edge in get_city_network()["edges"]}
    for group in caltrain_groups:
        assert all(
            edges[edge_id]["operator"] == "Caltrain"
            for edge_id in group["original_path"]
        )
        assert edges[group["original_path"][0]]["source"] == group["origin"]
        assert edges[group["original_path"][-1]]["target"] == group["destination"]
    assert any(
        event["operator"] == "Caltrain" and event["count"] > 0 for event in boarded
    )
    corridor_ids = {group["cohort_id"] for group in caltrain_groups}
    caltrain_boardings = [event for event in boarded if event["operator"] == "Caltrain" and event["cohort_id"] in corridor_ids]
    riders = sum(group["count"] for group in caltrain_groups)
    assert riders == 61
    assert (
        sum(event["count"] for event in caltrain_boardings if event["first_boarding"])
        == riders
    )
    assert sum(event["count"] for event in caltrain_boardings) == riders * 3
    group_ids = {group["cohort_id"] for group in caltrain_groups}
    assert (
        sum(
            event["count"]
            for frame in extended["frames"]
            for event in frame["passenger_events"]
            if event["action"] == "arrived" and event["cohort_id"] in group_ids
        )
        == riders
    )
