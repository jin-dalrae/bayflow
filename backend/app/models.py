"""The editable harness safety envelope; evaluation settings are intentionally absent."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

AGENTS = {
    "muni_agent",
    "bart_agent",
    "caltrain_agent",
    "regional_coordinator",
    "demand_forecaster",
}
TOOLS = {
    "local_dispatch_optimizer",
    "regional_coordination",
    "demand_forecast",
    "transfer_optimizer",
    "feasibility_checker",
    "service_frequency_optimizer",
    "passenger_advisory",
}
OPERATORS = Literal["Muni Bus", "Muni Metro", "BART", "Caltrain"]
# Each rule action is gated by the tool that grants it; the harness owns tool access.
RULE_ACTION_TOOLS = {
    "standby_dispatch": "local_dispatch_optimizer",
    "hold_for_transfer": "transfer_optimizer",
    "transfer_boarding_priority": "transfer_optimizer",
}


class PolicyParameters(BaseModel):
    """Controller thresholds the harness may tune. Defaults reproduce the original hand-set policy."""

    model_config = ConfigDict(extra="forbid")
    advisory_pressure_threshold: float = Field(default=0.45, ge=0.1, le=2.0)
    advisory_eta_slack_minutes: int = Field(default=10, ge=0, le=10)
    dispatch_threshold_regional: float = Field(default=0.35, ge=0.1, le=3.0)
    dispatch_threshold_local: float = Field(default=1.2, ge=0.2, le=3.0)
    urgent_wait_minutes: int = Field(default=7, ge=3, le=15)
    upstream_lookahead_minutes: int = Field(default=15, ge=0, le=60)
    upstream_weight: float = Field(default=0.5, ge=0.0, le=2.0)
    age_weight: float = Field(default=0.1, ge=0.0, le=1.0)
    persistence_weight: float = Field(default=0.002, ge=0.0, le=0.05)
    hold_load_fraction: float = Field(default=0.05, ge=0.0, le=0.3)


class OperatingRule(BaseModel):
    """Declarative trigger→action rule interpreted by the simulator; never executable code."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_]{3,40}$")
    description: str = Field(min_length=5, max_length=300)
    signal: Literal[
        "edge_queue_ratio",
        "oldest_wait_minutes",
        "incoming_transfer_riders",
        "unboarded_intent_minutes",
    ]
    comparator: Literal[">=", "<="] = ">="
    threshold: float = Field(ge=0, le=1000)
    scope_operators: list[OPERATORS] = Field(min_length=1, max_length=4)
    action: Literal["standby_dispatch", "hold_for_transfer", "transfer_boarding_priority"]
    max_hold_minutes: int = Field(default=0, ge=0, le=5)
    priority: float = Field(default=1.0, ge=0, le=10)
    enabled: bool = True

    @model_validator(mode="after")
    def coherent(self):
        if len(set(self.scope_operators)) != len(self.scope_operators):
            raise ValueError("Duplicate rule scope operator")
        if self.action == "hold_for_transfer" and self.max_hold_minutes < 1:
            raise ValueError("hold_for_transfer needs max_hold_minutes >= 1")
        if self.action != "hold_for_transfer" and self.max_hold_minutes:
            raise ValueError("max_hold_minutes only applies to hold_for_transfer")
        return self


class HarnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(default="v1", pattern=r"^v[0-9]+$")
    coordination_mode: Literal["decentralized", "hub_and_spoke", "regional"] = (
        "decentralized"
    )
    active_agents: list[str] = Field(
        default_factory=lambda: ["muni_agent", "bart_agent", "caltrain_agent"],
        min_length=1,
    )
    active_tools: list[str] = Field(
        default_factory=lambda: ["local_dispatch_optimizer"]
    )
    planning_horizon_minutes: int = Field(default=30, ge=10, le=120)
    replanning_interval_minutes: int = Field(default=15, ge=5, le=30, multiple_of=5)
    context_policy: Literal["local_only", "transfer_neighbors", "regional_shared"] = (
        "local_only"
    )
    memory_window_steps: int = Field(default=6, ge=1, le=48)
    verification_policy: Literal["basic", "strict"] = "basic"
    optimization_strategy: Literal[
        "local_greedy", "transfer_aware", "regional_predictive"
    ] = "local_greedy"
    policy: PolicyParameters = Field(default_factory=PolicyParameters)
    rules: list[OperatingRule] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def envelope(self):
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Duplicate rule id")
        for rule in self.rules:
            tool = RULE_ACTION_TOOLS[rule.action]
            if rule.enabled and tool not in self.active_tools:
                raise ValueError(f"Rule {rule.id} action {rule.action} requires tool {tool}")
            if (
                rule.enabled
                and rule.signal == "incoming_transfer_riders"
                and self.context_policy == "local_only"
            ):
                raise ValueError(
                    f"Rule {rule.id} observes other operators' arrivals; local_only context cannot see them"
                )
        if (
            len(set(self.active_agents)) != len(self.active_agents)
            or not set(self.active_agents) <= AGENTS
        ):
            raise ValueError("Unknown or duplicate agents")
        if (
            len(set(self.active_tools)) != len(self.active_tools)
            or not set(self.active_tools) <= TOOLS
        ):
            raise ValueError("Unknown or duplicate tools")
        if (
            self.coordination_mode != "decentralized"
            and "regional_coordinator" not in self.active_agents
        ):
            raise ValueError("Regional coordination requires regional_coordinator")
        if (
            "demand_forecast" in self.active_tools
            and "demand_forecaster" not in self.active_agents
        ):
            raise ValueError("Forecast tool requires demand_forecaster")
        if set(self.active_tools) & {"service_frequency_optimizer", "passenger_advisory"} and (
            self.coordination_mode == "decentralized" or "regional_coordinator" not in self.active_agents
        ):
            raise ValueError("Regional service and advisory tools require a coordinating harness")
        return self
