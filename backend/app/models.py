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
}


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

    @model_validator(mode="after")
    def envelope(self):
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
        return self
