"""City-scale synthetic commute experiment on observed GTFS connectivity.

Segment calendars are phased along routes. This is a capacity/queue model, not
complete vehicle blocks or a live agency dispatcher. Demand, compliance and the
initial ETA are fixed independently of the harness and evaluator.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
import heapq
import math
import random
from .city_network import get_city_network, get_city_demand_pairs
from .agents import OPERATOR_AGENTS, create_operator_controllers, transfer_priority
from .city_scenarios import get_city_scenario, active_profile_events

CITY_EVALUATOR = {
    "version": "city-intent-v2",
    "boarding_within_10": 0.35,
    "arrival_within_eta_10": 0.35,
    "crowding_exposure": 0.20,
    "operating_cost": 0.10,
    "unsafe_action_penalty": 1000,
    "boarding_limit_minutes": 10,
    "eta_slack_minutes": 10,
    "crowded_density_threshold": 1.5,
    "crowding_normalization_minutes": 30,
    "cost_normalization_units": 20000,
    "reference": "Initial undisrupted requested-path ETA is frozen before any advisory; unfinished requests fail arrival target.",
}


@dataclass
class Rider:
    count: int
    path: list
    step: int
    born: int
    reference: int
    ready: int
    cohort_id: str
    origin: str
    destination: str
    first_boarded: bool = False
    transfer: bool = False
    missed: bool = False


def simulate_city(
    config,
    seed=42,
    mode="fixed",
    demand_scale=1.0,
    advisory_acceptance_rate=0.6,
    horizon_minutes=180,
    city_profile="standard",
):
    if (
        not isinstance(horizon_minutes, int)
        or isinstance(horizon_minutes, bool)
        or not 180 <= horizon_minutes <= 1440
    ):
        raise ValueError("horizon_minutes must be an integer from180 to1440")
    if not 0.25 <= demand_scale <= 3 or not 0 <= advisory_acceptance_rate <= 1:
        raise ValueError("Invalid fixed scenario parameters")
    profile = get_city_scenario(city_profile)
    requested_demand_scale = demand_scale
    requested_acceptance_rate = advisory_acceptance_rate
    demand_scale *= profile.demand_multiplier
    if profile.acceptance_override is not None:
        advisory_acceptance_rate = profile.acceptance_override
    net = get_city_network(horizon_minutes=horizon_minutes)
    nodes = {n["id"]: n for n in net["nodes"]}
    edges = {e["id"]: e for e in net["edges"]}
    adjacency = defaultdict(list)
    for edge in edges.values():
        adjacency[edge["source"]].append(edge)
    rng = random.Random(seed)
    compliance = random.Random(seed + 918273)
    queues = defaultdict(list)
    moving = []
    frames = []
    traces = []
    groups = []
    events = []
    advisories = []
    reserve = defaultdict(list)
    limits = net["resource_limits"]
    controllers = create_operator_controllers(config)
    generated = served = wait_total = delay_total = first_boarded = within10 = (
        eta_on_time
    ) = 0
    transfer_count = missed_count = capacity_denials = extra_cost = extra_departures = (
        service_holds
    ) = 0
    violations = capacity_violations = exposure = max_queue = 0
    peak_density = 0.0
    gross_dispatch_cost = 0
    dispatch_budget = 12000
    offered = accepted = 0
    od_generated = defaultdict(int)
    od_arrived = defaultdict(int)
    route_cache = {}
    group_lookup = {}
    current_minute = 0
    policy = config.policy
    held = {}
    active_rule_edges = {}
    telemetry = {
        r.id: dict(
            action=r.action,
            evaluations=0,
            fired=0,
            dispatches=0,
            holds=0,
            hold_minutes=0,
            riders_affected=0,
        )
        for r in config.rules
    }
    price = {"Muni Bus": 90, "Muni Metro": 160, "BART": 400, "Caltrain": 350}
    regional = (
        config.coordination_mode != "decentralized"
        and config.context_policy != "local_only"
        and "regional_coordination" in config.active_tools
        and "regional_coordinator" in config.active_agents
    )
    coordinated_service = (
        regional and "service_frequency_optimizer" in config.active_tools
    )
    guidance = regional and "passenger_advisory" in config.active_tools

    def departure(time, edge):
        offset = edge.get("departure_offset_minutes", 0)
        h = edge["headway_minutes"]
        return math.ceil((time - offset) / h) * h + offset

    def expected(path, born):
        clock = born
        for eid in path:
            e = edges[eid]
            if e["operator"] != "walk":
                clock = departure(clock, e)
            clock += e["travel_minutes"]
        return clock

    def find_route(origin, destination, avoid=None, congested=False, preferred=None):
        key = (origin, destination, preferred)
        if not avoid and not congested and key in route_cache:
            return route_cache[key]
        heap = [(0, origin, "", False, [])]
        best = {}
        while heap:
            cost, node, previous, used_preferred, path = heapq.heappop(heap)
            state = (node, previous, used_preferred)
            if cost >= best.get(state, float("inf")):
                continue
            best[state] = cost
            if node == destination and (not preferred or used_preferred):
                if not avoid and not congested:
                    route_cache[key] = path
                return path
            for e in adjacency[node]:
                service = (
                    e.get("route_id", e["service"]) + ":" + str(e.get("direction", ""))
                    if e["operator"] != "walk"
                    else ""
                )
                entering = service != previous and bool(service)
                added = e["travel_minutes"] + (
                    e["headway_minutes"] / 2 if entering else 0
                )
                if entering and e["operator"] == avoid:
                    added += 25
                if entering and congested:
                    added += min(
                        35,
                        sum(c.count for c in queues.get(e["id"], []))
                        / e["capacity"]
                        * e["headway_minutes"],
                    )
                heapq.heappush(
                    heap,
                    (
                        cost + added,
                        e["target"],
                        service,
                        used_preferred or e["operator"] == preferred,
                        path + [e["id"]],
                    ),
                )
        return None

    def incoming_transfers(eid, minute, window):
        # GTFS platforms have distinct IDs: transfers include explicit walking links.
        # Forecast only already-moving riders and walk duration, not future demand.
        arrivals = []
        target_op = edges[eid]["operator"]
        for vehicle in moving:
            for rider in vehicle["cohorts"]:
                previous = next(
                    (
                        edges[x]["operator"]
                        for x in reversed(rider.path[: rider.step + 1])
                        if edges[x]["operator"] != "walk"
                    ),
                    None,
                )
                if not previous or previous == target_op:
                    continue
                index = rider.step + 1
                arrival = vehicle["arrival"]
                while (
                    index < len(rider.path)
                    and edges[rider.path[index]]["operator"] == "walk"
                ):
                    arrival += edges[rider.path[index]]["travel_minutes"]
                    index += 1
                if (
                    index < len(rider.path)
                    and rider.path[index] == eid
                    and minute < arrival <= minute + window
                ):
                    arrivals.append((arrival, rider.count))
        return arrivals

    def log(action, c, minute, **details):
        events.append(
            dict(
                action=action,
                cohort_id=c.cohort_id,
                count=c.count,
                origin=c.origin,
                destination=c.destination,
                minute=minute,
                **details,
            )
        )

    def create_group(pair, count, minute, path, reference, parent=None):
        nonlocal generated, transfer_count
        gid = f"city-group-{len(groups)+1:04d}"
        c = Rider(
            count,
            path,
            0,
            minute,
            reference,
            minute,
            gid,
            pair["origin"],
            pair["destination"],
        )
        catalog = dict(
            cohort_id=gid,
            count=count,
            origin=c.origin,
            destination=c.destination,
            born=minute,
            reference_arrival=reference,
            path=path,
            cluster=pair["cluster"],
            parent_intent=parent,
            requested_operator=pair.get("preferred_operator")
            or next(
                (
                    edges[e]["operator"]
                    for e in pair.get("requested_path", path)
                    if edges[e]["operator"] != "walk"
                ),
                "walk",
            ),
            original_path=pair.get("requested_path", path),
        )
        groups.append(catalog)
        group_lookup[gid] = catalog
        queues[path[0]].append(c)
        od_generated[(c.origin, c.destination)] += count
        generated += count
        prior = None
        for eid in path:
            op = edges[eid]["operator"]
            if op != "walk":
                if prior and prior != op:
                    transfer_count += count
                prior = op
        log("generated", c, minute, node=c.origin)
        return c

    pairs = get_city_demand_pairs()
    residential = [p for p in pairs if not p.get("route_id")]
    births = defaultdict(list)
    # Every actual route receives a small route-local intent stream; other OD demand is residential.
    for pair in pairs:
        if pair.get("route_id"):
            minute = rng.randrange(0, 61)
            births[minute].append(
                (pair, max(1, round(rng.randint(8, 16) * demand_scale)))
            )
    for minute in range(0, 121):
        for _ in range(3):
            pair = rng.choice(residential)
            births[minute].append(
                (pair, max(1, round(rng.randint(14, 30) * demand_scale)))
            )
    # Extended demand is a fixed synthetic day profile, never a harness-controlled forecast.
    # Appending future requests preserves every RNG draw for the original 180-minute scenario.
    outbound = [pair for pair in residential if pair["direction"] == "outbound"]
    inbound = [pair for pair in residential if pair["direction"] == "inbound"]
    for minute in range(121, max(120, horizon_minutes - 60) + 1):
        hour = (16 + minute // 60) % 24
        if 18 <= hour < 23:
            requests = 1
            pool = outbound
        elif hour >= 23 or hour < 6:
            requests = 1 if minute % 3 == 0 else 0
            pool = residential
        elif 6 <= hour < 9:
            requests = 4
            pool = inbound
        else:
            requests = 2
            pool = residential
        for _ in range(requests):
            pair = rng.choice(pool)
            births[minute].append(
                (pair, max(1, round(rng.randint(14, 30) * demand_scale)))
            )
    if horizon_minutes > 180:
        # The GTFS reference includes Muni/BART. Exercise the separately documented
        # selected Caltrain corridor with explicit, valid, frozen rail intents.
        caltrain_rng = random.Random(seed + 361027)
        rail_intents = [
            (
                125,
                "sf_caltrain",
                "millbrae_caltrain",
                ["sf_caltrain-22nd", "22nd-bayshore", "bayshore-millbrae_caltrain"],
            ),
            (
                155,
                "millbrae_caltrain",
                "sf_caltrain",
                ["millbrae_caltrain-bayshore", "bayshore-22nd", "22nd-sf_caltrain"],
            ),
            (
                185,
                "sf_caltrain",
                "millbrae_caltrain",
                ["sf_caltrain-22nd", "22nd-bayshore", "bayshore-millbrae_caltrain"],
            ),
        ]
        for minute, origin, destination, path in rail_intents:
            if minute > horizon_minutes:
                continue
            if any(
                edge_id not in edges or edges[edge_id]["operator"] != "Caltrain"
                for edge_id in path
            ):
                raise ValueError(
                    "Selected Caltrain commute intent requires valid corridor edges"
                )
            pair = dict(
                origin=origin,
                destination=destination,
                cluster="Selected Caltrain corridor",
                route_id="Caltrain:SF-Millbrae",
                preferred_operator="Caltrain",
                path=path,
                provenance="Synthetic seeded commute demand on the derived selected Caltrain corridor; not observed ridership or full Caltrain GTFS",
            )
            births[minute].append(
                (pair, max(1, round(caltrain_rng.randint(10, 30) * demand_scale)))
            )
    if profile.stadium_multiplier > 1:
        for minute, requests in births.items():
            if profile.stadium_start <= minute < profile.stadium_end:
                births[minute] = [
                    (
                        pair,
                        (
                            count * profile.stadium_multiplier
                            if pair.get("downtown") == "Mission Bay"
                            and pair.get("direction") == "outbound"
                            else count
                        ),
                    )
                    for pair, count in requests
                ]
    # Precompute requested paths independent of subsequent queue pressure and harness.
    for minute, requests in births.items():
        births[minute] = [
            (
                dict(p, intent_id=f"intent-{minute:03d}-{i:03d}"),
                count,
                p.get("path") or find_route(p["origin"], p["destination"]),
                [compliance.random() for _ in range(count)],
            )
            for i, (p, count) in enumerate(requests)
        ]
    # Some residential commuters prefer BART even where another provider is viable.
    # Their requested path and ETA are established before any harness observes demand.
    preferences = random.Random(seed + 675849)
    preferred_cache = {}
    for minute, requests in births.items():
        adjusted = []
        for pair, count, path, willingness in requests:
            if not pair.get("route_id") and preferences.random() < 0.35:
                key = (pair["origin"], pair["destination"])
                if key not in preferred_cache:
                    preferred_cache[key] = find_route(*key, preferred="BART")
                requested = preferred_cache[key]
                if (
                    requested
                    and expected(requested, minute) <= expected(path, minute) + 20
                ):
                    path = requested
                    pair = dict(pair, preferred_operator="BART")
            adjusted.append((pair, count, path, willingness))
        births[minute] = adjusted
    end = horizon_minutes
    for minute in range(end + 1):
        current_minute = minute
        events = []
        advisories = []
        remaining = []
        for v in moving:
            if v["arrival"] > minute:
                remaining.append(v)
                continue
            for c in v["cohorts"]:
                e = edges[c.path[c.step]]
                log(
                    "leg_arrival",
                    c,
                    minute,
                    node=e["target"],
                    edge_id=e["id"],
                    operator=e["operator"],
                    vehicle_id=v["id"],
                )
                if c.step + 1 == len(c.path):
                    served += c.count
                    od_arrived[(c.origin, c.destination)] += c.count
                    delay_total += max(0, minute - c.reference) * c.count
                    if minute <= c.reference + CITY_EVALUATOR["eta_slack_minutes"]:
                        eta_on_time += c.count
                    log(
                        "arrived",
                        c,
                        minute,
                        node=c.destination,
                        delay_minutes=max(0, minute - c.reference),
                    )
                    continue
                nxt = edges[c.path[c.step + 1]]
                oldop = next(
                    (
                        edges[x]["operator"]
                        for x in reversed(c.path[: c.step + 1])
                        if edges[x]["operator"] != "walk"
                    ),
                    None,
                )
                transfer = (
                    nxt["operator"] != "walk" and oldop and oldop != nxt["operator"]
                )
                queues[nxt["id"]].append(
                    replace(
                        c,
                        step=c.step + 1,
                        ready=minute,
                        transfer=bool(transfer),
                        missed=False,
                    )
                )
        moving = remaining
        for operator in limits:
            reserve[operator] = [t for t in reserve[operator] if t > minute]
        for pair, count, path, willingness in births.get(minute, []):
            pair = dict(pair, requested_path=path)
            if not path:
                raise ValueError("Disconnected declared commute intent")
            reference = expected(path, minute)
            alt = None
            pressure = 0
            preferred = pair.get("preferred_operator") or next(
                (edges[e]["operator"] for e in path if edges[e]["operator"] != "walk"),
                "walk",
            )
            # Guidance is triggered by measured queue pressure on the requested path, never random invented alerts.
            if guidance and mode != "static":
                pressure = max(
                    (
                        sum(c.count for c in queues.get(eid, []))
                        / max(1, edges[eid]["capacity"])
                        for eid in path
                        if edges[eid]["operator"] != "walk"
                    ),
                    default=0,
                )
                if pressure > policy.advisory_pressure_threshold:
                    candidate = find_route(
                        pair["origin"],
                        pair["destination"],
                        avoid=preferred,
                        congested=True,
                    )
                    if (
                        candidate
                        and candidate != path
                        and expected(candidate, minute)
                        <= reference + policy.advisory_eta_slack_minutes
                    ):
                        oldscore = sum(
                            sum(c.count for c in queues.get(e, []))
                            / max(1, edges[e]["capacity"])
                            for e in path
                        )
                        newscore = sum(
                            sum(c.count for c in queues.get(e, []))
                            / max(1, edges[e]["capacity"])
                            for e in candidate
                        )
                        if newscore < oldscore:
                            alt = candidate
            if alt:
                # Separate seeded Bernoulli decisions preserve demand RNG and total population across interventions.
                follows = sum(value < advisory_acceptance_rate for value in willingness)
                offered += count
                accepted += follows
                targetop = next(
                    (
                        edges[e]["operator"]
                        for e in alt
                        if edges[e]["operator"] != "walk"
                    ),
                    "walk",
                )
                requested_service = next(
                    (
                        edges[e]["service"]
                        for e in path
                        if edges[e]["operator"] != "walk"
                    ),
                    "walk",
                )
                alternative_service = next(
                    (
                        edges[e]["service"]
                        for e in alt
                        if edges[e]["operator"] != "walk"
                    ),
                    "walk",
                )
                sign = dict(
                    minute=minute,
                    agent="regional_coordinator",
                    tool="passenger_advisory",
                    action="passenger_advisory",
                    node=pair["origin"],
                    origin=pair["origin"],
                    destination=pair["destination"],
                    requested_operator=preferred,
                    alternative_operator=targetop,
                    requested_service=requested_service,
                    alternative_service=alternative_service,
                    offered_count=count,
                    accepted_count=follows,
                    initial_eta=reference,
                    alternative_eta=expected(alt, minute),
                    rationale="Voluntary valid-route alternative has lower observed queue pressure and stays within initial ETA + 10 minutes.",
                    message=f"{preferred} {requested_service} is crowded in this simulation. Consider {targetop} {alternative_service} for a less crowded journey.",
                    harness_version=config.version,
                )
                traces.append(sign)
                advisories.append(sign)
                if follows:
                    create_group(
                        pair, follows, minute, alt, reference, parent=pair["intent_id"]
                    )
                if count - follows:
                    create_group(
                        pair,
                        count - follows,
                        minute,
                        path,
                        reference,
                        parent=pair["intent_id"],
                    )
            else:
                create_group(
                    pair, count, minute, path, reference, parent=pair["intent_id"]
                )
        if mode != "static" and minute % config.replanning_interval_minutes == 0:
            visible = {eid: edges[eid] for eid, q in queues.items() if q}
            for controller in controllers.values():
                snapshot = controller.observe(minute, queues, visible, [])
                # Observations are real but bounded for planner context; full state remains in frames.
                snapshot["observed_queues"] = dict(
                    sorted(
                        snapshot["observed_queues"].items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:25]
                )
                snapshot["local_edges"] = snapshot["local_edges"][:25]
                snapshot["observation_scope"] = (
                    "Top 25 nonempty visible edges; totals include all visible queues"
                )
                traces.append(snapshot)
        # Typed rules are evaluated on real observations only at replanning ticks.
        if mode != "static" and minute % config.replanning_interval_minutes == 0:
            active_rule_edges = {}
            candidates = set(eid for eid, q in queues.items() if q)
            for vehicle in moving:
                if vehicle["arrival"] <= minute + min(
                    config.planning_horizon_minutes, policy.upstream_lookahead_minutes
                ):
                    for rider in vehicle["cohorts"]:
                        index = rider.step + 1
                        while (
                            index < len(rider.path)
                            and edges[rider.path[index]]["operator"] == "walk"
                        ):
                            index += 1
                        if index < len(rider.path):
                            candidates.add(rider.path[index])
            for eid in sorted(candidates):
                e = edges[eid]
                q = queues[eid]
                op = e["operator"]
                if op == "walk" or OPERATOR_AGENTS.get(op) not in config.active_agents:
                    continue
                incoming = incoming_transfers(
                    eid,
                    minute,
                    min(
                        config.planning_horizon_minutes,
                        policy.upstream_lookahead_minutes,
                    ),
                )
                signals = dict(
                    edge_queue_ratio=sum(c.count for c in q) / e["capacity"],
                    oldest_wait_minutes=max((minute - c.ready for c in q), default=0),
                    unboarded_intent_minutes=max(
                        (minute - c.born for c in q if not c.first_boarded), default=0
                    ),
                    incoming_transfer_riders=sum(count for arrival, count in incoming),
                )
                for rule in sorted(config.rules, key=lambda r: r.id):
                    if not rule.enabled or op not in rule.scope_operators:
                        continue
                    telemetry[rule.id]["evaluations"] += 1
                    value = signals[rule.signal]
                    fires = (
                        value >= rule.threshold
                        if rule.comparator == ">="
                        else value <= rule.threshold
                    )
                    if not fires:
                        continue
                    telemetry[rule.id]["fired"] += 1
                    active_rule_edges.setdefault(eid, []).append(rule)
                    traces.append(
                        dict(
                            tool="operating_rule",
                            rule_id=rule.id,
                            action=rule.action,
                            edge_id=eid,
                            operator=op,
                            minute=minute,
                            signal_value=value,
                            harness_version=config.version,
                        )
                    )
        supplements = set()
        if (
            mode != "static"
            and "local_dispatch_optimizer" in config.active_tools
            and minute % config.replanning_interval_minutes == 0
        ):
            scores = []
            for eid, q in queues.items():
                if not q:
                    continue
                e = edges[eid]
                op = e["operator"]
                agent = OPERATOR_AGENTS.get(op)
                if op == "walk" or agent not in config.active_agents:
                    continue
                if not op.startswith("Muni") and not coordinated_service:
                    continue
                count = sum(c.count for c in q)
                oldest = max(minute - c.ready for c in q)
                upstream = 0
                if regional:
                    upstream = sum(
                        c.count
                        for v in moving
                        if v["arrival"]
                        <= minute
                        + min(
                            policy.upstream_lookahead_minutes,
                            config.planning_horizon_minutes,
                        )
                        for c in v["cohorts"]
                        if c.step + 1 < len(c.path) and c.path[c.step + 1] == eid
                    )
                pressure = count + policy.upstream_weight * upstream
                urgent = regional and any(
                    not c.first_boarded
                    and minute - c.born >= policy.urgent_wait_minutes
                    for c in q
                )
                dispatch_rules = [
                    r
                    for r in active_rule_edges.get(eid, [])
                    if r.action == "standby_dispatch"
                ]
                if (
                    pressure
                    > e["capacity"]
                    * (
                        policy.dispatch_threshold_regional
                        if regional
                        else policy.dispatch_threshold_local
                    )
                    or urgent
                    or dispatch_rules
                ):
                    history = frames[-config.memory_window_steps :]
                    persistent = sum(
                        f["queues"].get(e["source"], 0) for f in history
                    ) / max(1, len(history))
                    scores.append(
                        (
                            pressure / e["capacity"]
                            + oldest * policy.age_weight
                            + persistent * policy.persistence_weight
                            + sum(r.priority for r in dispatch_rules),
                            eid,
                        )
                    )
            for score, eid in sorted(scores, reverse=True):
                e = edges[eid]
                op = e["operator"]
                if (
                    len(reserve[op]) >= limits[op]
                    or gross_dispatch_cost + price[op] > dispatch_budget
                ):
                    continue
                if (
                    config.verification_policy == "strict"
                    and minute + e["travel_minutes"] > end
                ):
                    continue
                supplements.add(eid)
                reserve[op].append(minute + max(15, e["travel_minutes"] * 2 + 5))
                extra_cost += price[op]
                gross_dispatch_cost += price[op]
                extra_departures += 1
                for rule in active_rule_edges.get(eid, []):
                    if rule.action == "standby_dispatch":
                        telemetry[rule.id]["dispatches"] += 1
                        telemetry[rule.id]["riders_affected"] += min(
                            e["capacity"], sum(c.count for c in queues[eid])
                        )
                traces.append(
                    dict(
                        minute=minute,
                        agent=(
                            "regional_coordinator" if regional else OPERATOR_AGENTS[op]
                        ),
                        provider_agent=OPERATOR_AGENTS[op],
                        tool=(
                            "service_frequency_optimizer"
                            if coordinated_service
                            else "local_dispatch_optimizer"
                        ),
                        action="standby_dispatch",
                        edge_id=eid,
                        operator=op,
                        observed_queue=sum(c.count for c in queues[eid]),
                        rationale="Prioritize late travel intents and shared transfer pressure within fixed standby vehicle/driver limits.",
                        harness_version=config.version,
                    )
                )
        for eid, q in list(queues.items()):
            if (
                not q
                and eid not in held
                and not any(
                    r.action == "hold_for_transfer"
                    for r in active_rule_edges.get(eid, [])
                )
            ):
                continue
            e = edges[eid]
            op = e["operator"]
            held_due = eid in held and held[eid]["due"] == minute
            scheduled = held_due or (eid not in held and minute == departure(minute, e))
            disrupted = False
            bart_delay_minutes = 0
            held_rule = held[eid]["rule_id"] if held_due else None
            if held_due:
                del held[eid]
            if (
                profile.standard_disruptions
                and op == "Muni Bus"
                and e["service"] == "22"
                and 30 <= minute < 75
                and (minute - e.get("departure_offset_minutes", 0)) % 30 == 15
            ):
                scheduled = False
                disrupted = True
            if (
                profile.standard_disruptions
                and op == "BART"
                and e["source"] in {"BART:EMBR", "BART:MONT", "BART:POWL"}
                and 45 <= minute < 75
            ):
                disrupted = True
            if disrupted and op == "BART":
                bart_delay_minutes = 3
            if (
                profile.bus_gap_route
                and op == "Muni Bus"
                and e["service"] == profile.bus_gap_route
                and profile.bus_gap_start <= minute < profile.bus_gap_end
                and (
                    (minute - e.get("departure_offset_minutes", 0))
                    // e["headway_minutes"]
                )
                % 2
                == 1
            ):
                scheduled = False
                disrupted = True
            if (
                profile.bart_delay_minutes
                and op == "BART"
                and e["source"] in {"BART:EMBR", "BART:MONT", "BART:POWL"}
                and profile.bart_delay_start <= minute < profile.bart_delay_end
            ):
                disrupted = True
                bart_delay_minutes = max(bart_delay_minutes, profile.bart_delay_minutes)
            if (
                mode != "static"
                and scheduled
                and not held_due
                and not disrupted
                and op != "walk"
            ):
                for rule in sorted(
                    active_rule_edges.get(eid, []),
                    key=lambda r: r.priority,
                    reverse=True,
                ):
                    if rule.action != "hold_for_transfer":
                        continue
                    incoming = incoming_transfers(eid, minute, rule.max_hold_minutes)
                    if not incoming:
                        continue
                    due = min(arrival for arrival, count in incoming)
                    held[eid] = dict(due=due, rule_id=rule.id)
                    scheduled = False
                    affected = sum(c.count for c in q) + sum(
                        count for arrival, count in incoming if arrival == due
                    )
                    telemetry[rule.id]["holds"] += 1
                    telemetry[rule.id]["hold_minutes"] += due - minute
                    telemetry[rule.id]["riders_affected"] += affected
                    traces.append(
                        dict(
                            tool="transfer_optimizer",
                            action="hold_for_transfer",
                            rule_id=rule.id,
                            edge_id=eid,
                            operator=op,
                            minute=minute,
                            due_minute=due,
                            hold_minutes=due - minute,
                            riders_affected=affected,
                            harness_version=config.version,
                            rationale="Defer one existing departure for incoming inter-operator riders; no capacity or fleet added.",
                        )
                    )
                    break
            if (
                coordinated_service
                and mode != "static"
                and scheduled
                and not held_due
                and eid not in supplements
                and op != "walk"
            ):
                oldest = max((minute - c.ready for c in q), default=0)
                next_wait = e["headway_minutes"] + oldest
                # Low-load holds are allowed only when the next regular service remains inside the boarding target.
                if (
                    sum(c.count for c in q) < e["capacity"] * policy.hold_load_fraction
                    and next_wait <= 10
                ):
                    scheduled = False
                    service_holds += 1
                    extra_cost -= price[op] * 0.25
                    traces.append(
                        dict(
                            minute=minute,
                            agent="regional_coordinator",
                            provider_agent=OPERATOR_AGENTS[op],
                            tool="service_frequency_optimizer",
                            action="service_hold",
                            edge_id=eid,
                            operator=op,
                            observed_queue=sum(c.count for c in q),
                            rationale="Skip this low-load modeled departure; next departure stays within the fixed ten-minute waiting envelope.",
                            harness_version=config.version,
                        )
                    )
            if not scheduled and eid not in supplements:
                wait_total += sum(c.count for c in q)
                continue
            seats = e["capacity"] * (int(scheduled) + int(eid in supplements))
            boarding = []
            leftover = []
            priority_rules = [
                r
                for r in active_rule_edges.get(eid, [])
                if r.action == "transfer_boarding_priority"
            ]
            if "transfer_optimizer" in config.active_tools and (
                config.optimization_strategy != "local_greedy" or priority_rules
            ):
                transfer_priority(q)
            for rule in priority_rules:
                telemetry[rule.id]["riders_affected"] += min(
                    seats, sum(c.count for c in q if c.transfer)
                )
            for c in q:
                count = min(seats, c.count)
                if count:
                    boarding.append(replace(c, count=count))
                    seats -= count
                if count < c.count:
                    rest = replace(c, count=c.count - count)
                    leftover.append(rest)
                    wait_total += rest.count
                    if op != "walk":
                        capacity_denials += rest.count
                        traces.append(
                            dict(
                                minute=minute,
                                tool="passenger_queue",
                                action="boarding_denied",
                                edge_id=eid,
                                operator=op,
                                count=rest.count,
                                transfer=rest.transfer,
                                wait_minutes=minute - rest.ready,
                                harness_version=config.version,
                            )
                        )
                        if rest.transfer and not rest.missed:
                            missed_count += rest.count
                            rest.missed = True
            queues[eid] = leftover
            packs = [[]]
            used = 0
            for c in boarding:
                amount = c.count
                while amount:
                    if used == e["capacity"]:
                        packs.append([])
                        used = 0
                    n = min(amount, e["capacity"] - used)
                    packs[-1].append(replace(c, count=n))
                    used += n
                    amount -= n
            duration = e["travel_minutes"] + bart_delay_minutes
            for index, pack in enumerate(packs):
                if not pack:
                    continue
                vid = f"{minute}:{eid}:{index}"
                carried = []
                for c in pack:
                    first = op != "walk" and not c.first_boarded
                    if first:
                        first_boarded += c.count
                        if minute - c.born <= 10:
                            within10 += c.count
                    log(
                        "walking" if op == "walk" else "boarded",
                        c,
                        minute,
                        node=e["source"],
                        target=e["target"],
                        edge_id=eid,
                        operator=op,
                        vehicle_id=vid,
                        arrival_minute=minute + duration,
                        first_boarding=first,
                    )
                    carried.append(replace(c, first_boarded=c.first_boarded or first))
                moving.append(
                    dict(
                        id=vid,
                        edge_id=eid,
                        source=e["source"],
                        target=e["target"],
                        operator=op,
                        departure=minute,
                        arrival=minute + duration,
                        capacity=e["capacity"],
                        cohorts=carried,
                    )
                )
        node_queues = defaultdict(int)
        for eid, q in queues.items():
            node_queues[edges[eid]["source"]] += sum(c.count for c in q)
        node_queues = {n: c for n, c in node_queues.items() if c}
        max_queue = max(max_queue, max(node_queues.values(), default=0))
        crowded = []
        regional_density = 0
        for node, count in node_queues.items():
            area = (
                400
                if "BART" in nodes[node].get("operators", [])
                else 180 if "Muni Metro" in nodes[node].get("operators", []) else 25
            )
            density = count / area
            regional_density = max(regional_density, density)
            if density > CITY_EVALUATOR["crowded_density_threshold"]:
                exposure += count
                crowded.append(
                    dict(
                        node=node, count=count, density=round(density, 3), area_m2=area
                    )
                )
        peak_density = max(peak_density, regional_density)
        capacity_violations += sum(
            max(0, sum(c.count for c in v["cohorts"]) - v["capacity"]) for v in moving
        )
        violations += sum(max(0, len(reserve[op]) - limits[op]) for op in limits)
        flows = {
            key: dict(
                origin=key[0],
                destination=key[1],
                generated=count,
                waiting=0,
                walking=0,
                riding=0,
                arrived=od_arrived[key],
            )
            for key, count in od_generated.items()
        }
        for q in queues.values():
            for c in q:
                flows[(c.origin, c.destination)]["waiting"] += c.count
        for v in moving:
            for c in v["cohorts"]:
                flows[(c.origin, c.destination)][
                    "walking" if v["operator"] == "walk" else "riding"
                ] += c.count
        balance = dict(
            generated=generated,
            arrived=served,
            waiting=sum(f["waiting"] for f in flows.values()),
            walking=sum(f["walking"] for f in flows.values()),
            riding=sum(f["riding"] for f in flows.values()),
        )
        balance["conserved"] = generated == sum(
            balance[k] for k in ("arrived", "waiting", "walking", "riding")
        )
        frames.append(
            dict(
                minute=minute,
                time=f"{(16+minute//60)%24:02}:{minute%60:02}",
                day_offset=(16 * 60 + minute) // 1440,
                queues=node_queues,
                vehicles=[
                    dict(
                        id=v["id"],
                        edge_id=v["edge_id"],
                        source=v["source"],
                        target=v["target"],
                        operator=v["operator"],
                        progress=round(
                            (minute - v["departure"]) / (v["arrival"] - v["departure"]),
                            3,
                        ),
                        occupancy=sum(c.count for c in v["cohorts"]),
                        capacity=v["capacity"],
                        passenger_groups=[
                            dict(
                                cohort_id=c.cohort_id,
                                count=c.count,
                                origin=c.origin,
                                destination=c.destination,
                            )
                            for c in v["cohorts"]
                        ],
                    )
                    for v in moving
                ],
                events=active_profile_events(profile, minute),
                served=served,
                generated=generated,
                passenger_balance=balance,
                passenger_flows=list(flows.values()),
                passenger_events=events,
                advisories=advisories,
                passenger_service=dict(
                    intent_count=generated,
                    first_boarded=first_boarded,
                    boarded_within_10=within10,
                    boarding_within_10_minutes_rate=within10 / max(1, first_boarded),
                    eta_on_time_arrived=eta_on_time,
                    arrived=served,
                    eta_within_10_minutes_rate=eta_on_time / max(1, served),
                    regional_density=round(regional_density, 3),
                    crowded_locations=sorted(
                        crowded, key=lambda c: c["density"], reverse=True
                    )[:10],
                    advisory_offered=offered,
                    advisory_accepted=accepted,
                ),
            )
        )
    balance = frames[-1]["passenger_balance"]
    unserved = generated - served
    terminal = sum(
        c.count * max(0, end - c.reference + 30) for q in queues.values() for c in q
    ) + sum(
        c.count * max(0, end - c.reference + 30) for v in moving for c in v["cohorts"]
    )
    delay_total += terminal
    board_rate = within10 / max(1, generated)
    eta_rate = eta_on_time / max(1, generated)
    objective = (
        0.35 * (1 - board_rate)
        + 0.35 * (1 - eta_rate)
        + 0.20 * exposure / max(1, generated * 30)
        + 0.10 * max(0, extra_cost) / 20000
        + 1000 * (violations + capacity_violations)
    )
    metrics = dict(
        total_passenger_delay_minutes=delay_total,
        average_passenger_delay=round(delay_total / max(1, generated), 3),
        missed_transfer_rate=round(missed_count / max(1, transfer_count), 5),
        missed_transfers=missed_count,
        transfer_opportunities=transfer_count,
        passenger_wait_time=round(wait_total / max(1, generated), 3),
        total_passenger_wait_minutes=wait_total,
        congestion=capacity_denials,
        max_station_queue=max_queue,
        capacity_violations=capacity_violations,
        feasibility_violations=violations,
        unserved_passengers=unserved,
        additional_operating_cost=round(extra_cost, 3),
        extra_departures=extra_departures,
        service_holds=service_holds,
        generated_passengers=generated,
        served_passengers=served,
        objective=round(objective, 6),
        first_boarded_passengers=first_boarded,
        boarded_within_10_minutes=within10,
        boarding_within_10_minutes_rate=round(board_rate, 6),
        eta_on_time_arrived=eta_on_time,
        eta_within_10_minutes_rate=round(eta_rate, 6),
        regional_density_peak=round(peak_density, 3),
        crowding_exposure_passenger_minutes=exposure,
        advisory_offered_passengers=offered,
        advisory_accepted_passengers=accepted,
        active_services=len(
            {
                edges[e["edge_id"]]["route_id"]
                for f in frames
                for e in f["passenger_events"]
                if e["action"] == "boarded"
            }
        ),
    )
    return dict(
        metrics=metrics,
        frames=frames,
        traces=traces,
        rule_telemetry=telemetry,
        passenger_groups=groups,
        config=config.model_dump(),
        seed=seed,
        mode=mode,
        scenario="city_commute",
        scenario_parameters=dict(
            demand_scale=demand_scale,
            advisory_acceptance_rate=advisory_acceptance_rate,
            horizon_minutes=horizon_minutes,
            **(
                {
                    "city_profile": city_profile,
                    "requested_demand_scale": requested_demand_scale,
                    "requested_advisory_acceptance_rate": requested_acceptance_rate,
                }
                if city_profile != "standard"
                else {}
            ),
        ),
        **({"city_profile": profile.metadata()} if city_profile != "standard" else {}),
        evaluator=CITY_EVALUATOR,
        horizon_minutes=end,
        time_step_minutes=1,
        start_hour=16,
        frame_interval_minutes=1,
        synthetic_demand_schedule=dict(
            initial="Original scenario:3residential requests/minute0–120 plus one small intent stream per actual route",
            extended="Afterminute120:18–23 one outbound request/minute;23–06 one request/3minutes;06–09 four inbound requests/minute;otherwise two requests/minute. Demandstops60minutes before end, never beforeminute120. Counts14–30 riders before demand_scale.",
            observed=False,
            supplemental_caltrain="For horizons above180min, seeded10–30-rider intents at minutes125/155/185 on selected SF–Millbrae corridor, within horizon. Separate derived service, not part of82 GTFS reference routes.",
            service_availability="Synthetic interval services continue overnight; actual agency operating-hour closures are not modeled.",
        ),
        accounting=dict(
            generated=generated,
            served=served,
            queued=balance["waiting"],
            onboard=balance["walking"] + balance["riding"],
            conserved=balance["conserved"],
        ),
        resource_constraints=f"Fixed city standby vehicle/driver pairs: {limits}; gross supplemental-service budget {dispatch_budget} model cost units. No evaluator, intent demand, initial ETA or acceptance seed mutation.",
        data_provenance="Agency GTFS connectivity snapshots; synthetic demand, speed/headway/capacity, queue areas and incidents; no real-time passenger data",
    )
