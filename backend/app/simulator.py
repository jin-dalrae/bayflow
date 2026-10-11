"""Seeded cohort simulator. All metrics derive from passenger and vehicle events."""

from collections import defaultdict
from dataclasses import dataclass, replace
import heapq
import math
import random
from .models import HarnessConfig
from .network import get_network
from .agents import OPERATOR_AGENTS, create_operator_controllers, transfer_priority

EVALUATOR = {
    "version": "objective-v1",
    "delay": 0.50,
    "missed_transfers": 0.20,
    "unserved": 0.20,
    "operating_cost": 0.10,
    "unsafe_action_penalty": 1000,
    "reference": "Earliest journey on the same selected path with undisrupted published synthetic headways and unlimited capacity.",
}


@dataclass
class Cohort:
    count: int
    path: list
    step: int
    born: int
    reference: int
    ready: int
    transfer: bool = False
    missed: bool = False


def simulate(config=None, seed=42, mode="fixed", scenario="event_surge"):
    config = (
        config if isinstance(config, HarnessConfig) else HarnessConfig(**(config or {}))
    )
    if mode not in {"static", "fixed", "evolving"}:
        raise ValueError("Mode must be static, fixed or evolving")
    if scenario not in {"event_surge", "commuter", "accident"}:
        raise ValueError("Unknown scenario")
    rng = random.Random(seed)
    net = get_network()
    edges = {e["id"]: e for e in net["edges"]}
    adj = defaultdict(list)
    for e in edges.values():
        adj[e["source"]].append(e)

    def route(origin, destination):
        heap = [(0, origin, [])]
        seen = set()
        while heap:
            cost, node, path = heapq.heappop(heap)
            if node == destination:
                return path
            if node in seen:
                continue
            seen.add(node)
            for e in adj[node]:
                heapq.heappush(
                    heap,
                    (
                        cost
                        + e["travel_minutes"]
                        + (0 if e["operator"] == "walk" else e["headway_minutes"] / 2),
                        e["target"],
                        path + [e["id"]],
                    ),
                )
        raise ValueError("Disconnected demand")

    queues = defaultdict(list)
    moving = []
    frames = []
    traces = []
    reserve = []
    generated = served = wait_total = delay_total = transfer_count = missed_count = (
        extra_cost
    ) = extra_departures = 0
    max_queue = capacity_denials = 0
    capacity_violations = feasibility_violations = 0
    arrivals_by_operator = defaultdict(int)
    routes = {}
    controllers = create_operator_controllers(config)

    def generate(origin, destination, count, minute):
        nonlocal generated, transfer_count
        key = (origin, destination)
        if key not in routes:
            routes[key] = route(*key)
        path = routes[key]
        reference = minute
        previous = None
        for eid in path:
            edge = edges[eid]
            if edge["operator"] != "walk":
                reference = (
                    math.ceil(reference / edge["headway_minutes"])
                    * edge["headway_minutes"]
                )
                if previous and previous != edge["operator"]:
                    transfer_count += count
                previous = edge["operator"]
            reference += edge["travel_minutes"]
        queues[path[0]].append(Cohort(count, path, 0, minute, reference, minute))
        generated += count

    for minute in range(0, 421, 5):
        # Arriving cohorts and physical vehicles release their capacity.
        remaining = []
        for vehicle in moving:
            if vehicle["arrival"] > minute:
                remaining.append(vehicle)
                continue
            for cohort in vehicle["cohorts"]:
                old = edge = edges[cohort.path[cohort.step]]
                next_step = cohort.step + 1
                if next_step == len(cohort.path):
                    served += cohort.count
                    delay_total += max(0, minute - cohort.reference) * cohort.count
                    continue
                nxt = edges[cohort.path[next_step]]
                prev_operator = next(
                    (
                        edges[e]["operator"]
                        for e in reversed(cohort.path[:next_step])
                        if edges[e]["operator"] != "walk"
                    ),
                    None,
                )
                transfer = (
                    nxt["operator"] != "walk"
                    and prev_operator is not None
                    and nxt["operator"] != prev_operator
                )
                queues[nxt["id"]].append(
                    replace(
                        cohort,
                        step=next_step,
                        ready=minute,
                        transfer=transfer,
                        missed=False,
                    )
                )
                arrivals_by_operator[nxt["operator"]] += cohort.count
        moving = remaining
        if minute < 330:
            # Paired commute streams plus genuine interagency journeys.
            for origin, destination, base in [
                ("emb", "millbrae", 15),
                ("sf_caltrain", "millbrae_caltrain", 11),
                ("townsend", "balboa", 9),
                ("balboa", "ucsf", 7),
                ("powell", "oracle", 8),
            ]:
                generate(
                    origin, destination, rng.randint(max(1, base - 4), base + 4), minute
                )
        if scenario != "commuter":
            if 285 <= minute < 325:
                generate(
                    "chase",
                    rng.choice(["balboa", "millbrae", "civic"]),
                    rng.randint(95, 135),
                    minute,
                )
            if 330 <= minute < 365:
                generate(
                    "oracle",
                    rng.choice(["millbrae_caltrain", "balboa", "millbrae"]),
                    rng.randint(105, 145),
                    minute,
                )
        events = []
        if 80 <= minute < 170:
            events.append(
                {
                    "type": "driver_shortage",
                    "label": "Muni bus driver unavailable · every second departure canceled",
                }
            )
        if scenario != "commuter" and 130 <= minute < 190:
            events.append(
                {
                    "type": "delay",
                    "label": "BART downtown disruption · canceled trips + 5 min delay",
                }
            )
        if 285 <= minute < 325 and scenario != "commuter":
            events.append(
                {"type": "surge", "label": "Fictional Chase Center event egress"}
            )
        if 330 <= minute < 365 and scenario != "commuter":
            events.append(
                {"type": "surge", "label": "Fictional Oracle Park event egress"}
            )
        if scenario == "accident" and 250 <= minute < 290:
            events.append(
                {"type": "accident", "label": "Synthetic Third Street interruption"}
            )
        if mode != "static" and minute % config.replanning_interval_minutes == 0:
            for controller in controllers.values():
                traces.append(controller.observe(minute, queues, edges, events))
        # Every mutation field below affects observations, policy, frequency or prioritization.
        supplements = set()
        reserve = [t for t in reserve if t > minute]
        if (
            mode != "static"
            and "local_dispatch_optimizer" in config.active_tools
            and minute % config.replanning_interval_minutes == 0
        ):
            scores = []
            regional = (
                config.coordination_mode != "decentralized"
                and config.context_policy != "local_only"
                and "regional_coordination" in config.active_tools
            )
            # Reserve expansion requires observable corridor overload, not just access to shared context.
            # One regular departure per distinct Muni service is the corridor capacity envelope.
            service_capacities = {
                e["service"]: e["capacity"]
                for e in edges.values()
                if e["operator"].startswith("Muni")
            }
            corridor_capacity = sum(service_capacities.values())
            corridor_queue = sum(
                c.count
                for eid, q in queues.items()
                if edges[eid]["operator"].startswith("Muni")
                for c in q
            )
            regional_overload = regional and corridor_queue > corridor_capacity
            for eid, q in queues.items():
                e = edges[eid]
                agent = (
                    "muni_agent"
                    if e["operator"].startswith("Muni")
                    else ("bart_agent" if e["operator"] == "BART" else "caltrain_agent")
                )
                if agent not in config.active_agents or e["operator"] not in {
                    "Muni Metro",
                    "Muni Bus",
                }:
                    continue
                count = sum(c.count for c in q)
                threshold = e["capacity"] * (0.45 if regional_overload else 1.2)
                pressure = count
                if regional:
                    # Neighbor context sees arriving transfer partners; shared context sees the corridor.
                    lookahead = (
                        config.planning_horizon_minutes
                        if config.context_policy == "regional_shared"
                        else min(15, config.planning_horizon_minutes)
                    )
                    pressure += sum(
                        c.count * 0.5
                        for v in moving
                        for c in v["cohorts"]
                        if c.step + 1 < len(c.path)
                        and c.path[c.step + 1] == eid
                        and v["arrival"] <= minute + lookahead
                    )
                if (
                    "demand_forecast" in config.active_tools
                    and config.optimization_strategy == "regional_predictive"
                ):
                    if e["source"] in {"ucsf", "king_muni"} and any(
                        0 <= event_min - minute <= config.planning_horizon_minutes
                        for event_min in [285, 330]
                    ):
                        pressure += 80
                if pressure > threshold:
                    oldest = max((minute - c.ready for c in q), default=0)
                    history = frames[-config.memory_window_steps :]
                    persistent = sum(
                        f["queues"].get(e["source"], 0) for f in history
                    ) / max(1, len(history))
                    scores.append(
                        (pressure / e["capacity"] + oldest / 10 + persistent / 500, eid)
                    )
            for pressure, eid in sorted(scores, reverse=True):
                if len(reserve) >= 3:
                    break
                e = edges[eid]
                if e["operator"] == "Muni Bus" and 80 <= minute < 170:
                    continue
                if (
                    scenario == "accident"
                    and e["service"] == "T"
                    and 250 <= minute < 290
                ):
                    continue
                verified = (
                    config.verification_policy == "strict"
                    or "feasibility_checker" in config.active_tools
                )
                if verified and (not queues[eid] or minute + e["travel_minutes"] > 420):
                    continue
                # A pool of 3 standby vehicle/driver pairs; each occupies a turn cycle.
                supplements.add(eid)
                reserve.append(minute + e["travel_minutes"] * 2 + 5)
                extra_departures += 1
                extra_cost += 90 if e["operator"] == "Muni Bus" else 160
                traces.append(
                    {
                        "minute": minute,
                        "agent": "regional_coordinator" if regional else "muni_agent",
                        "tool": (
                            "regional_coordination"
                            if regional
                            else "local_dispatch_optimizer"
                        ),
                        "action": "standby_dispatch",
                        "edge_id": eid,
                        "observed_queue": sum(c.count for c in queues[eid]),
                        "corridor_queue": corridor_queue,
                        "corridor_capacity": corridor_capacity,
                        "regional_overload": regional_overload,
                        "rationale": (
                            "Shared transfer pressure"
                            if regional
                            else "Local queue exceeds capacity"
                        ),
                        "harness_version": config.version,
                        "verification": (
                            "strict resource and horizon check"
                            if verified
                            else "resource envelope"
                        ),
                    }
                )
        for eid, e in edges.items():
            q = queues[eid]
            if not q:
                continue
            scheduled = minute % e["headway_minutes"] == 0
            if e["operator"] == "Muni Bus" and 80 <= minute < 170 and minute % 30 == 15:
                scheduled = False
            disrupted = (
                scenario != "commuter"
                and e["operator"] == "BART"
                and 130 <= minute < 190
            )
            if disrupted and minute % 30 == 15:
                scheduled = False
            if scenario == "accident" and e["service"] == "T" and 250 <= minute < 290:
                scheduled = False
            if not scheduled and eid not in supplements:
                wait_total += sum(c.count for c in q) * 5
                continue
            capacity = e["capacity"] * (
                (1 if scheduled else 0) + (1 if eid in supplements else 0)
            )
            edge_agent = OPERATOR_AGENTS.get(e["operator"])
            if edge_agent in controllers:
                priority_trace = controllers[edge_agent].prioritize_boarding(
                    q, e, minute, capacity
                )
                if priority_trace:
                    traces.append(priority_trace)
            elif (
                e["operator"] == "walk"
                and "caltrain_agent" in config.active_agents
                and config.optimization_strategy != "local_greedy"
                and "transfer_optimizer" in config.active_tools
            ):
                # Preserve the existing transfer-walk cohort ordering; unlimited walk capacity
                # makes this infrastructure ordering rather than an operator intervention.
                transfer_priority(q)
            boarded = []
            leftover = []
            seats = capacity
            for c in q:
                n = min(seats, c.count)
                if n:
                    boarded.append(replace(c, count=n))
                    seats -= n
                if n < c.count:
                    left = replace(c, count=c.count - n)
                    if e["operator"] != "walk":
                        capacity_denials += left.count
                        if left.transfer and not left.missed:
                            missed_count += left.count
                            left.missed = True
                    leftover.append(left)
            for c in leftover:
                wait_total += c.count * 5
            queues[eid] = leftover
            if boarded:
                duration = e["travel_minutes"] + (5 if disrupted else 0)
                # Supplemental service is a separate physical vehicle, never a larger nominal vehicle.
                packs = [[]]
                used = 0
                for cohort in boarded:
                    remaining_count = cohort.count
                    while remaining_count:
                        if used == e["capacity"]:
                            packs.append([])
                            used = 0
                        n = min(remaining_count, e["capacity"] - used)
                        packs[-1].append(replace(cohort, count=n))
                        used += n
                        remaining_count -= n
                for vehicle_index, pack in enumerate(packs):
                    suffix = "" if vehicle_index == 0 else f"-standby{vehicle_index}"
                    moving.append(
                        {
                            "id": f"{minute}-{eid}{suffix}",
                            "edge_id": eid,
                            "source": e["source"],
                            "target": e["target"],
                            "operator": e["operator"],
                            "departure": minute,
                            "arrival": minute + duration,
                            "capacity": e["capacity"],
                            "cohorts": pack,
                        }
                    )
        # Count canceled connections independently of capacity denials.
        for eid, q in queues.items():
            e = edges[eid]
            for c in q:
                if (
                    c.transfer
                    and not c.missed
                    and minute - c.ready > e["headway_minutes"]
                ):
                    missed_count += c.count
                    c.missed = True
        node_queues = defaultdict(int)
        for eid, q in queues.items():
            node_queues[edges[eid]["source"]] += sum(c.count for c in q)
        max_queue = max(max_queue, max(node_queues.values(), default=0))
        capacity_violations += sum(
            max(0, sum(c.count for c in v["cohorts"]) - v["capacity"]) for v in moving
        )
        feasibility_violations += max(0, len(reserve) - 3)
        for v in moving:
            if v["departure"] != minute:
                continue
            edge = edges[v["edge_id"]]
            forbidden = (
                edge["operator"] == "Muni Bus"
                and 80 <= minute < 170
                and minute % 30 == 15
            ) or (
                scenario == "accident"
                and edge["service"] == "T"
                and 250 <= minute < 290
            )
            feasibility_violations += int(forbidden)
        frames.append(
            {
                "minute": minute,
                "time": f"{16+minute//60:02}:{minute%60:02}",
                "queues": dict(node_queues),
                "vehicles": [
                    {
                        "id": v["id"],
                        "edge_id": v["edge_id"],
                        "source": v["source"],
                        "target": v["target"],
                        "operator": v["operator"],
                        "progress": round(
                            (minute - v["departure"]) / (v["arrival"] - v["departure"]),
                            3,
                        ),
                        "occupancy": sum(c.count for c in v["cohorts"]),
                        "capacity": v["capacity"],
                    }
                    for v in moving
                ],
                "events": events,
                "served": served,
                "generated": generated,
            }
        )
    queued = sum(c.count for q in queues.values() for c in q)
    onboard = sum(c.count for v in moving for c in v["cohorts"])
    unserved = queued + onboard
    # Terminal delay charge prevents postponing or abandoning passengers to improve fitness.
    terminal_delay = sum(
        c.count * max(0, 420 - c.reference + 30) for q in queues.values() for c in q
    ) + sum(
        c.count * max(0, 420 - c.reference + 30) for v in moving for c in v["cohorts"]
    )
    delay_total += terminal_delay
    average_delay = delay_total / max(1, generated)
    missed_rate = missed_count / max(1, transfer_count)
    objective = (
        0.50 * (average_delay / 30)
        + 0.20 * missed_rate
        + 0.20 * (unserved / max(1, generated))
        + 0.10 * (extra_cost / 20000)
        + EVALUATOR["unsafe_action_penalty"]
        * (capacity_violations + feasibility_violations)
    )
    metrics = {
        "total_passenger_delay_minutes": round(delay_total, 2),
        "average_passenger_delay": round(average_delay, 3),
        "missed_transfer_rate": round(missed_rate, 5),
        "missed_transfers": missed_count,
        "transfer_opportunities": transfer_count,
        "passenger_wait_time": round(wait_total / max(1, generated), 3),
        "total_passenger_wait_minutes": wait_total,
        "congestion": capacity_denials,
        "max_station_queue": max_queue,
        "capacity_violations": capacity_violations,
        "feasibility_violations": feasibility_violations,
        "unserved_passengers": unserved,
        "additional_operating_cost": extra_cost,
        "extra_departures": extra_departures,
        "generated_passengers": generated,
        "served_passengers": served,
        "objective": round(objective, 6),
    }
    return {
        "metrics": metrics,
        "frames": frames,
        "traces": traces,
        "config": config.model_dump(),
        "seed": seed,
        "mode": mode,
        "scenario": scenario,
        "evaluator": EVALUATOR,
        "accounting": {
            "generated": generated,
            "served": served,
            "queued": queued,
            "onboard": onboard,
            "conserved": generated == served + queued + onboard,
        },
        "data_provenance": "Fully synthetic demand and incidents on selected real Bay Area connections",
    }
