"""Deterministic operator controllers; architecture review belongs to the planner.

Controllers observe real queue state and apply the enabled transfer-priority tool.
They never invent vehicles, compute evaluation scores, or call an LLM.
"""

from dataclasses import dataclass, field

OPERATOR_AGENTS = {
    "Muni Bus": "muni_agent",
    "Muni Metro": "muni_agent",
    "BART": "bart_agent",
    "Caltrain": "caltrain_agent",
}


def transfer_priority(queue):
    """Stable in-place boarding policy shared by transit and transfer-walk queues."""
    queue.sort(key=lambda cohort: (not cohort.transfer, cohort.reference, cohort.born))


@dataclass
class OperatorController:
    name: str
    config: object
    observations: list = field(default_factory=list)

    def observe(self, minute, queues, edges, events):
        local_ids = {
            eid
            for eid, edge in edges.items()
            if OPERATOR_AGENTS.get(edge["operator"]) == self.name
        }
        visible_ids = set(local_ids)
        if self.config.context_policy == "regional_shared":
            visible_ids = {
                eid for eid, edge in edges.items() if edge["operator"] != "walk"
            }
        elif self.config.context_policy == "transfer_neighbors":
            local_nodes = {
                edges[eid][key] for eid in local_ids for key in ("source", "target")
            }
            transfer_nodes = set(local_nodes)
            for edge in edges.values():
                if edge["operator"] == "walk" and (
                    edge["source"] in local_nodes or edge["target"] in local_nodes
                ):
                    transfer_nodes.update((edge["source"], edge["target"]))
            visible_ids.update(
                eid
                for eid, edge in edges.items()
                if edge["operator"] != "walk"
                and (
                    edge["source"] in transfer_nodes or edge["target"] in transfer_nodes
                )
            )
        counts = {
            eid: sum(cohort.count for cohort in queues.get(eid, []))
            for eid in sorted(visible_ids)
        }
        local_event_types = {
            "muni_agent": {"driver_shortage", "accident", "surge"},
            "bart_agent": {"delay"},
            "caltrain_agent": set(),
        }[self.name]
        visible_events = [
            event
            for event in events
            if (
                self.config.context_policy != "local_only"
                or event["type"] in local_event_types
            )
        ]
        snapshot = {
            "minute": minute,
            "agent": self.name,
            "action": "observe",
            "context_policy": self.config.context_policy,
            "observed_queues": counts,
            "observed_queue": sum(counts.values()),
            "local_edges": sorted(local_ids),
            "events": visible_events,
            "planning_horizon_minutes": self.config.planning_horizon_minutes,
            "harness_version": self.config.version,
        }
        self.observations.append(snapshot)
        self.observations = self.observations[-self.config.memory_window_steps :]
        snapshot["retained_observations"] = len(self.observations)
        return snapshot

    def prioritize_boarding(self, queue, edge, minute, capacity):
        if not (
            "transfer_optimizer" in self.config.active_tools
            and self.config.optimization_strategy != "local_greedy"
        ):
            return None
        transfer_priority(queue)
        return {
            "minute": minute,
            "agent": self.name,
            "tool": "transfer_optimizer",
            "action": "boarding_priority",
            "edge_id": edge["id"],
            "operator": edge["operator"],
            "observed_queue": sum(cohort.count for cohort in queue),
            "transfer_passengers": sum(
                cohort.count for cohort in queue if cohort.transfer
            ),
            "available_capacity": capacity,
            "rationale": "Board transfer cohorts first, then earliest reference arrival; deterministic capacity allocation follows.",
            "harness_version": self.config.version,
        }


def create_operator_controllers(config):
    return {
        name: OperatorController(name, config)
        for name in dict.fromkeys(OPERATOR_AGENTS.values())
        if name in config.active_agents
    }
